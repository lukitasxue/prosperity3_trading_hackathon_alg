
import json
from typing import List, Dict, Tuple, Any
from datamodel import OrderDepth, Order, TradingState, Symbol, ProsperityEncoder

class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: Dict[Symbol, List[Order]], conversions: int, trader_data: str) -> None:
        base_length = len(self.to_json([
            self.compress_state(state, ""),
            self.compress_orders(orders),
            conversions, "", ""
        ]))
        max_item_length = (self.max_log_length - base_length) // 3
        print(self.to_json([
            self.compress_state(state, self.truncate(state.traderData, max_item_length)),
            self.compress_orders(orders),
            conversions,
            self.truncate(trader_data, max_item_length),
            self.truncate(self.logs, max_item_length)
        ]))
        self.logs = ""

    def compress_state(self, state: TradingState, trader_data: str) -> List[Any]:
        return [
            state.timestamp,
            trader_data,
            [[l.symbol, l.product, l.denomination] for l in state.listings.values()],
            {s: [od.buy_orders, od.sell_orders] for s, od in state.order_depths.items()},
            [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp] for trades in state.own_trades.values() for t in trades],
            [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp] for trades in state.market_trades.values() for t in trades],
            state.position,
            [state.observations.plainValueObservations, {
                p: [
                    o.bidPrice, o.askPrice, o.transportFees,
                    o.exportTariff, o.importTariff,
                    o.sugarPrice, o.sunlightIndex
                ] for p, o in state.observations.conversionObservations.items()
            }]
        ]

    def compress_orders(self, orders: Dict[Symbol, List[Order]]) -> List[List[Any]]:
        return [[o.symbol, o.price, o.quantity] for order_list in orders.values() for o in order_list]

    def to_json(self, value: Any) -> str:
        return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

    def truncate(self, value: str, max_length: int) -> str:
        return value if len(value) <= max_length else value[:max_length - 3] + "..."

logger = Logger()

# Each tick (iteration), your run() function receives the state, which includes:

# state.order_depths: Buy/Sell orders for each product

# state.position: Your current holdings

# state.own_trades: What your bot traded recently

# state.market_trades: What other bots traded

# state.timestamp: Time of the tick

# state.traderData: Info you saved from last tick (optional)

class Trader:

    def __init__(self):
        # track the price where we entered the trade for each product
        self.entry_price = {}

        # tracks wheter we currently hold a position in the product
        self.position_side = {}

        # product we are focusing on with this TP/SL technique
        self.product = "RAINFOREST_RESIN"

        # limits from prosperity
        self.position_limit = 50

        # profit and loss thresholds 
        self.take_profit_threshold = 3
        self.stop_loss_threshold = 2

    
    def run(self, state: TradingState) -> Tuple[Dict[Symbol, List[Order]], int, str]:
        logger.print(f"--- Tick {state.timestamp} ---")


        #holds the final orders we will return
        orders = []

        # get the current order depth (buy/sell book)
        order_depth = state.order_depths.get(self.product, None)
        if not order_depth:
            return {}, 0, ""

        # sort buy and sell prices
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None 
        best_ask = min(order_depth.buy_orders.keys()) if order_depth.sell_orders else None # lowest price someone is willing to sell at rn
           
        # get current positioin (default to 0 if not holding)
        current_position = state.position.get(self.product, 0)

        logger.print(f"Current position: {current_position}, best bid: {best_bid}, best ask: {best_ask}")


        # Entry logic: if we still dont own any resin, and see a seller offering it for a good price, then buy some

        # if we are not in a position, we can decide to buy
        if current_position == 0 and best_ask is not None: #currently hold 0 units?, is there a price available to buy {best ask}? 
            buy_price = best_ask # lowest price someone is willing to sell at rn, we decide to buy at that price
            buy_volume = min(order_depth.sell_orders[best_ask], self.position_limit) # number of units available at that best price, how many we are allowed to own (max 50), 
                # so we buy the smallest quantity of units to not exced the limit

            #save entry price and side
            self.entry_price[self.product] = buy_price # the price we bought at, used for later cimparison so we know when to sell
            self.position_side[self.product] = "long" # we are in a long position, (holding resin, expectin it to go up)

            orders.append(Order(self.product, buy_price, buy_volume)) # place buy order at that price, for that volume
            logger.print(f"Placing buy for {buy_volume} at {buy_price}") # log action


        # if we have some resin, and there are ppl willing to buy, lets see if we should sell it
        elif current_position > 0 and best_bid is not None: # if we are not holding 0 units, and there is a price someone is selling at
            entry = self.entry_price.get(self.product, None) # fetch price we bought at

            if entry:
                # calc PnL
                gain = best_bid - entry 

                #take profit
                if gain >= self.take_profit_threshold: #if profit is equal or greater than the threshold, then sell
                    sell_volume = current_position 
                    orders.append(Order(self.product, best_bid, -sell_volume)) # sell everything we own, at the best price available (best bid)
                    logger.print(f"Take Profit TRIGGERED: Selling {sell_volume} at {best_bid}") 
                    self.entry_price[self.product] = None # clear stored entry price

                # stop loss
                elif gain <= -self.stop_loss_threshold:  #if profit is equal or less than the threshold, then buy
                    sell_volume = current_position
                    orders.append(Order(self.product, best_bid, -sell_volume)) # sell all at the best bid (even if taking loss)
                    logger.print(f"Stop loss TRIGGERED: Selling {sell_volume} at {best_bid}")
                    self.entry_price[self.product] = None # clear the stored entry price


        logger.print(f"End of Tick {state.timestamp} — PnL so far: {self.pnl.get(self.product, 0)}")
        logger.flush(state, {self.product: orders}, 0, "")
        return {self.product: orders}, 0, ""
