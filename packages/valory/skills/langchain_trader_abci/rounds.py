# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2024 Valory AG
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------

"""This package contains the rounds of LangchainTraderAbciApp."""

import json
from enum import Enum
from typing import Dict, FrozenSet, Optional, Set, Tuple

from packages.valory.skills.abstract_round_abci.base import (
    AbciApp,
    AbciAppTransitionFunction,
    AppState,
    BaseSynchronizedData,
    CollectSameUntilThresholdRound,
    DegenerateRound,
    EventToTimeout,
    get_name,
)
from packages.valory.skills.langchain_trader_abci.payloads import (
    DecisionMakingPayload,
    PostTxDecisionMakingPayload,
)
from packages.valory.skills.mech_interact_abci.states.base import (
    SynchronizedData as MechSyncedData,
)


class Event(Enum):
    """LangchainTraderAbciApp Events"""

    DECISION_MAKING = "decision_making"
    MECH = "mech"
    SETTLE = "settle"
    DONE = "done"
    NO_MAJORITY = "no_majority"
    ROUND_TIMEOUT = "round_timeout"


class SynchronizedData(MechSyncedData):
    """
    Class to represent the synchronized data.

    This data is replicated by the tendermint application.
    """

    @property
    def post_tx_event(self) -> Optional[str]:
        """Get the post_tx_event."""
        return self.db.get("post_tx_event", None)


class DecisionMakingRound(CollectSameUntilThresholdRound):
    """DecisionMakingRound"""

    payload_class = DecisionMakingPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            payload = json.loads(self.most_voted_payload)
            event = Event(payload["event"])

            updates = {
                "mech_requests": json.dumps(payload["mech_requests"], sort_keys=True),
                "mech_responses": json.dumps(payload["mech_responses"], sort_keys=True),
                "most_voted_tx_hash": payload["tx_hash"],
                "post_tx_event": payload["post_tx_event"],
                "chain_id": payload["chain_id"],
            }

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=self.synchronized_data_class,
                **updates,
            )

            return synchronized_data, event

            # Static checker needs events to be mentioned:
            # Event.DONE, Event.MECH, Event.SETTLE, Event.ROUND_TIMEOUT

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class PostTxDecisionMakingRound(CollectSameUntilThresholdRound):
    """PostTxDecisionMakingRound"""

    payload_class = PostTxDecisionMakingPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            return self.synchronized_data, Event(self.most_voted_payload)

            # Static checker needs events to be mentioned:
            # Event.MECH, Event.DECISION_MAKING, Event.ROUND_TIMEOUT

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class FinishedDecisionMakingMechRound(DegenerateRound):
    """FinishedDecisionMakingMechRound"""


class FinishedDecisionMakingSettleRound(DegenerateRound):
    """FinishedDecisionMakingSettleRound"""


class FinishedPostTxDecisionMakingMechRound(DegenerateRound):
    """FinishedPostTxDecisionMakingMechRound"""


class FinishedDecisionMakingResetRound(DegenerateRound):
    """FinishedDecisionMakingResetRound"""


class LangchainTraderAbciApp(AbciApp[Event]):
    """LangchainTraderAbciApp"""

    initial_round_cls: AppState = DecisionMakingRound
    initial_states: Set[AppState] = {
        PostTxDecisionMakingRound,
        DecisionMakingRound,
    }
    transition_function: AbciAppTransitionFunction = {
        DecisionMakingRound: {
            Event.MECH: FinishedDecisionMakingMechRound,
            Event.SETTLE: FinishedDecisionMakingSettleRound,
            Event.NO_MAJORITY: DecisionMakingRound,
            Event.ROUND_TIMEOUT: DecisionMakingRound,
            Event.DONE: FinishedDecisionMakingResetRound,
        },
        PostTxDecisionMakingRound: {
            Event.MECH: FinishedPostTxDecisionMakingMechRound,
            Event.DECISION_MAKING: DecisionMakingRound,
            Event.NO_MAJORITY: PostTxDecisionMakingRound,
            Event.ROUND_TIMEOUT: PostTxDecisionMakingRound,
        },
        FinishedDecisionMakingMechRound: {},
        FinishedDecisionMakingSettleRound: {},
        FinishedPostTxDecisionMakingMechRound: {},
        FinishedDecisionMakingResetRound: {},
    }
    final_states: Set[AppState] = {
        FinishedDecisionMakingMechRound,
        FinishedDecisionMakingSettleRound,
        FinishedPostTxDecisionMakingMechRound,
        FinishedDecisionMakingResetRound,
    }
    event_to_timeout: EventToTimeout = {}
    cross_period_persisted_keys: FrozenSet[str] = frozenset()
    db_pre_conditions: Dict[AppState, Set[str]] = {
        DecisionMakingRound: set(),
        PostTxDecisionMakingRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedDecisionMakingMechRound: set(),
        FinishedDecisionMakingSettleRound: {
            get_name(SynchronizedData.most_voted_tx_hash)
        },
        FinishedPostTxDecisionMakingMechRound: set(),
        FinishedDecisionMakingResetRound: set(),
    }
