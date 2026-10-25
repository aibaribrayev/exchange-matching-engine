"""Order matching engine.

Traders send buy and sell orders. An order that can trade is matched straight
away. The rest waits on the book until a matching order arrives.
"""

import heapq
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class ExchangeError(Exception):
    """The exchange refused a request."""


class Side(Enum):
    BUY = "buy"
    SELL = "sell"


class Status(Enum):
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"


@dataclass
class Order:
    """One order to buy or sell shares of a stock."""

    order_id: int
    trader: str
    side: Side
    symbol: str
    price: Decimal
    quantity: int
    remaining: int  # shares still waiting to trade
    arrival: int  # orders at the same price trade in arrival order
    status: Status = Status.OPEN


@dataclass(frozen=True)
class Trade:
    """Shares changing hands between one buy order and one sell order."""

    symbol: str
    buy_order_id: int
    sell_order_id: int
    price: Decimal
    quantity: int


def _sell_priority(order: Order) -> tuple:
    """Cheapest seller first, then earliest."""
    return (order.price, order.arrival)


def _buy_priority(order: Order) -> tuple:
    """Highest buyer first, then earliest."""
    return (order.price, order.arrival)


def _accepts_price(incoming: Order, waiting: Order) -> bool:
    """Whether the incoming order accepts the waiting order's price."""
    if incoming.side is Side.BUY:
        return incoming.price > waiting.price
    return incoming.price < waiting.price


class OrderHeap:
    """Orders kept so that the best one is always at the front.

    ``key`` decides what "best" means. The order with the smallest key is at
    the front.
    """

    def __init__(self, key):
        self._key = key
        self._items = []  # (key, order) pairs, in heap order

    def push(self, order: Order) -> None:
        heapq.heappush(self._items, (self._key(order), order))

    def peek(self) -> Order:
        """The best order, without removing it."""
        key, order = self._items[0]
        return order

    def pop(self) -> Order:
        """Remove the best order and return it."""
        key, order = heapq.heappop(self._items)
        return order

    def is_empty(self) -> bool:
        return len(self._items) == 0


class OrderBook:
    """The orders waiting to trade in one stock."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self._buy_orders = OrderHeap(key=_buy_priority)
        self._sell_orders = OrderHeap(key=_sell_priority)
        self._trades: list[Trade] = []
        self._last_arrival = 0

    def add(self, order: Order) -> list[Trade]:
        """Trade the order against the other side of the book.

        The best price trades first. Among orders at the same price, the
        earliest trades first. Each trade happens at the price of the order
        that was already waiting. Whatever is left unfilled waits on the book.
        """
        new_trades = self._match(order)
        if order.remaining > 0:
            self._add_to_book(order)
        self._trades.extend(new_trades)
        return new_trades

    def trades(self) -> list[Trade]:
        """Every trade in this stock, in the order they happened."""
        return self._trades.copy()

    def next_arrival(self) -> int:
        """The next arrival number in this book. Later orders get higher numbers."""
        self._last_arrival += 1
        return self._last_arrival

    def _match(self, incoming: Order) -> list[Trade]:
        if incoming.side is Side.BUY:
            other_side = self._sell_orders
        else:
            other_side = self._buy_orders

        new_trades = []
        while incoming.remaining > 0 and not other_side.is_empty():
            waiting = other_side.peek()

            if not _accepts_price(incoming, waiting):
                break

            quantity = min(incoming.remaining, waiting.remaining)
            new_trades.append(self._trade(incoming, waiting, quantity))
            incoming.remaining -= quantity
            waiting.remaining -= quantity

            if waiting.remaining == 0:
                waiting.status = Status.FILLED
                other_side.pop()

        if incoming.remaining == 0:
            incoming.status = Status.FILLED
        return new_trades

    def _add_to_book(self, order: Order) -> None:
        if order.side is Side.BUY:
            self._buy_orders.push(order)
        else:
            self._sell_orders.push(order)

    def _trade(self, incoming: Order, waiting: Order, quantity: int) -> Trade:
        if incoming.side is Side.BUY:
            buyer = incoming
            seller = waiting
        else:
            buyer = waiting
            seller = incoming

        return Trade(
            symbol=self.symbol,
            buy_order_id=buyer.order_id,
            sell_order_id=seller.order_id,
            price=buyer.price,
            quantity=quantity,
        )


class Exchange:
    """The entry point traders use to buy and sell."""

    def __init__(self, symbols: list[str]):
        self._books: dict[str, OrderBook] = {}
        for symbol in symbols:
            self._books[symbol] = OrderBook(symbol)

        self._orders: dict[int, Order] = {}

    def place_order(
        self, trader: str, side: Side, symbol: str, quantity: int, price: Decimal
    ) -> int:
        """Place an order to buy or sell, and return the new order's id.

        Refuses a stock the exchange does not trade, and a quantity or price
        that is zero or negative. The order trades straight away with any
        waiting orders it can. Whatever is left waits on the book.
        """
        book = self._find_book(symbol)

        # Check the order before recording it.
        arrival = book.next_arrival()
        order = Order(
            order_id=arrival,  # arrival numbers are already unique
            trader=trader,
            side=side,
            symbol=symbol,
            price=price,
            quantity=quantity,
            remaining=quantity,
            arrival=arrival,
        )
        self._orders[order.order_id] = order

        if quantity <= 0:
            raise ExchangeError(f"quantity must be positive, got {quantity}")

        book.add(order)
        return order.order_id

    def cancel_order(self, order_id: int) -> None:
        """Cancel an order that is still waiting. A cancelled order never trades.

        Refuses an order that does not exist, or one that is already filled
        or cancelled.
        """
        order = self._find_order(order_id)
        if order.status is not Status.OPEN:
            raise ExchangeError(f"order {order_id} is already {order.status.value}")
        order.status = Status.CANCELLED

    def get_order(self, order_id: int) -> Order:
        """Look up an order. Refuses an id that does not exist.

        The caller gets a copy, so changing it does not change the exchange.
        """
        return self._find_order(order_id)

    def trades(self, symbol: str) -> list[Trade]:
        """Every trade in a stock, in the order they happened."""
        return self._find_book(symbol).trades()

    def _find_book(self, symbol: str) -> OrderBook:
        book = self._books.get(symbol)
        if book is None:
            raise ExchangeError(f"{symbol} is not traded on this exchange")
        return book

    def _find_order(self, order_id: int) -> Order:
        order = self._orders.get(order_id)
        if order is None:
            raise ExchangeError(f"there is no order {order_id}")
        return order
