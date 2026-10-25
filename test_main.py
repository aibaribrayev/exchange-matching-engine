"""Tests for the order matching engine."""

import unittest
from decimal import Decimal

from main import Exchange, ExchangeError, Side, Status


class ExchangeTest(unittest.TestCase):
    """Sets up an exchange, with shortcuts for placing orders."""

    def setUp(self):
        self.exchange = Exchange(["AAPL", "MSFT"])

    def buy(self, trader, quantity, price, stock="AAPL"):
        """Place a buy order. The price is a string, like "100.50"."""
        return self.exchange.place_order(
            trader, Side.BUY, stock, quantity, Decimal(price)
        )

    def sell(self, trader, quantity, price, stock="AAPL"):
        """Place a sell order. The price is a string, like "100.50"."""
        return self.exchange.place_order(
            trader, Side.SELL, stock, quantity, Decimal(price)
        )

    def trades(self, stock="AAPL"):
        return self.exchange.trades(stock)


class TestPlaceOrder(ExchangeTest):

    def test_returns_the_id_of_the_new_order(self):
        order_id = self.buy("alice", 10, "100")

        self.assertEqual(self.exchange.get_order(order_id).trader, "alice")

    def test_every_order_gets_a_different_id(self):
        first = self.buy("alice", 10, "100")
        second = self.buy("bob", 10, "100")

        self.assertNotEqual(first, second)

    def test_refuses_a_stock_the_exchange_does_not_trade(self):
        with self.assertRaises(ExchangeError):
            self.buy("alice", 10, "100", stock="TSLA")

    def test_refuses_a_quantity_that_is_not_positive(self):
        with self.assertRaises(ExchangeError):
            self.buy("alice", 0, "100")
        with self.assertRaises(ExchangeError):
            self.buy("alice", -5, "100")


class TestMatching(ExchangeTest):

    def test_an_order_that_cannot_trade_waits(self):
        alice = self.sell("alice", 10, "100")
        self.buy("bob", 10, "95")

        self.assertEqual(self.trades(), [])
        self.assertEqual(self.exchange.get_order(alice).status, Status.OPEN)

    def test_a_trade_happens_at_the_waiting_orders_price(self):
        self.buy("carol", 10, "102")
        self.sell("alice", 10, "100")

        trades = self.trades()
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].price, Decimal("102"))
        self.assertEqual(trades[0].quantity, 10)

    def test_the_cheapest_seller_trades_first(self):
        self.sell("frank", 10, "101")
        alice = self.sell("alice", 10, "100")
        self.buy("carol", 10, "102")

        self.assertEqual(self.trades()[0].sell_order_id, alice)

    def test_the_highest_buyer_trades_first(self):
        self.buy("bob", 10, "95")
        self.buy("dan", 10, "98")
        self.sell("alice", 10, "94")

        self.assertEqual(len(self.trades()), 1)

    def test_at_the_same_price_the_earliest_order_trades_first(self):
        alice = self.sell("alice", 10, "100")
        self.sell("eve", 10, "100")
        self.buy("carol", 10, "101")

        self.assertEqual(self.trades()[0].sell_order_id, alice)

    def test_a_partly_filled_order_keeps_its_remaining_shares_waiting(self):
        alice = self.sell("alice", 10, "100")
        self.buy("carol", 4, "101")

        order = self.exchange.get_order(alice)
        self.assertEqual(order.remaining, 6)
        self.assertEqual(order.status, Status.OPEN)

    def test_one_order_can_trade_with_several_waiting_orders(self):
        self.sell("alice", 4, "100")
        self.sell("eve", 10, "100")
        carol = self.buy("carol", 10, "102")

        trades = self.trades()
        self.assertEqual(len(trades), 2)
        self.assertEqual(trades[0].quantity, 4)
        self.assertEqual(trades[1].quantity, 6)
        self.assertEqual(self.exchange.get_order(carol).status, Status.FILLED)

    def test_a_cancelled_order_does_not_trade(self):
        alice = self.sell("alice", 10, "100")
        eve = self.sell("eve", 10, "100")
        self.exchange.cancel_order(eve)
        self.buy("carol", 10, "101")

        self.assertEqual(self.trades()[0].sell_order_id, alice)

    def test_orders_in_different_stocks_never_trade(self):
        self.sell("alice", 10, "100", stock="MSFT")
        self.buy("carol", 10, "101", stock="AAPL")

        self.assertEqual(self.trades("AAPL"), [])
        self.assertEqual(self.trades("MSFT"), [])


class TestCancelOrder(ExchangeTest):

    def test_a_waiting_order_can_be_cancelled(self):
        alice = self.sell("alice", 10, "100")
        self.exchange.cancel_order(alice)

        self.assertEqual(self.exchange.get_order(alice).status, Status.CANCELLED)

    def test_refuses_an_order_that_is_already_filled(self):
        alice = self.sell("alice", 10, "100")
        self.buy("carol", 10, "101")

        with self.assertRaises(ExchangeError):
            self.exchange.cancel_order(alice)

    def test_refuses_an_order_that_is_already_cancelled(self):
        alice = self.sell("alice", 10, "100")
        self.exchange.cancel_order(alice)

        with self.assertRaises(ExchangeError):
            self.exchange.cancel_order(alice)

    def test_refuses_an_order_that_does_not_exist(self):
        with self.assertRaises(ExchangeError):
            self.exchange.cancel_order(999)


class TestGetOrder(ExchangeTest):

    def test_refuses_an_id_that_does_not_exist(self):
        with self.assertRaises(ExchangeError):
            self.exchange.get_order(999)


class TestTrades(ExchangeTest):

    def test_trades_are_listed_in_the_order_they_happened(self):
        self.sell("alice", 10, "100")
        carol = self.buy("carol", 4, "101")
        dan = self.buy("dan", 6, "101")

        trades = self.trades()
        self.assertEqual(trades[0].buy_order_id, carol)
        self.assertEqual(trades[1].buy_order_id, dan)


if __name__ == "__main__":
    unittest.main()
