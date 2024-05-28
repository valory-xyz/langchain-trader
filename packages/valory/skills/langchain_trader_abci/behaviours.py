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

"""This package contains round behaviours of LangchainTraderAbciApp."""

import json
import uuid
from abc import ABC
from dataclasses import asdict
from typing import Any, Dict, Generator, List, Optional, Set, Type, cast

from packages.valory.contracts.gnosis_safe.contract import GnosisSafeContract
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.abstract_round_abci.behaviours import (
    AbstractRoundBehaviour,
    BaseBehaviour,
)
from packages.valory.skills.langchain_trader_abci.models import Params, SharedState
from packages.valory.skills.langchain_trader_abci.payloads import (
    DecisionMakingPayload,
    PostTxDecisionMakingPayload,
)
from packages.valory.skills.langchain_trader_abci.rounds import (
    DecisionMakingRound,
    Event,
    LangchainTraderAbciApp,
    PostTxDecisionMakingRound,
    SynchronizedData,
)
from packages.valory.skills.mech_interact_abci.states.base import (
    MechInteractionResponse,
    MechMetadata,
)
from packages.valory.skills.transaction_settlement_abci.payload_tools import (
    hash_payload_to_hex,
)
from packages.valory.skills.transaction_settlement_abci.rounds import TX_HASH_LENGTH


# setting the safe gas to 0 means that all available gas will be used
# which is what we want in most cases
# more info here: https://safe-docs.dev.gnosisdev.com/safe/docs/contracts_tx_execution/
SAFE_GAS = 0
GNOSIS_CHAIN_ID = "gnosis"
VALUE_KEY = "value"
TO_ADDRESS_KEY = "to_address"
EXPECTED_CALL_DATA = frozenset({VALUE_KEY, TO_ADDRESS_KEY})
# the current POC only supports transfer transactions, therefore, the transaction data will always be empty
TX_DATA = b"0x"


class LangchainTraderBaseBehaviour(BaseBehaviour, ABC):
    """Base behaviour for the langchain_trader_abci skill."""

    @property
    def synchronized_data(self) -> SynchronizedData:
        """Return the synchronized data."""
        return cast(SynchronizedData, super().synchronized_data)

    @property
    def params(self) -> Params:
        """Return the params."""
        return cast(Params, super().params)

    @property
    def local_state(self) -> SharedState:
        """Return the state."""
        return cast(SharedState, self.context.state)


class DecisionMakingBehaviour(LangchainTraderBaseBehaviour):
    """DecisionMakingBehaviour"""

    matching_round: Type[AbstractRound] = DecisionMakingRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            payload_data = yield from self.get_payload_data()
            payload = DecisionMakingPayload(
                sender=self.context.agent_address,
                content=json.dumps(payload_data, sort_keys=True),
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_payload_data(self) -> Generator[None, None, Dict]:
        """Get the payload"""

        # Default payload data which clears everything before resetting
        data = dict(
            event=Event.DONE.value,
            mech_requests=[],
            mech_responses=[],
            tx_hash="",
            post_tx_event="",
            chain_id=GNOSIS_CHAIN_ID,
        )

        # If there are user requests, we need to send mech requests
        n_pending = len(self.local_state.user_requests)
        if n_pending:
            self.context.logger.info(f"{n_pending} pending user request(s).")
            data["event"] = Event.MECH.value
            data["mech_requests"] = self.get_mech_requests()
            # go back to mech response after settling
            data["post_tx_event"] = Event.MECH.value
            return data

        # If there are mech responses, we settle them
        mech_responses = self.synchronized_data.mech_responses
        if mech_responses:
            mech_response = mech_responses.pop(0)  # remove the response to be processed
            tx_hash = yield from self.process_next_mech_response(mech_response)
            data["mech_responses"] = [asdict(response) for response in mech_responses]

            # If the mech tool has decided not to trade, we skip trading.
            if not tx_hash:
                return data

            # We are settling a transaction
            data["event"] = Event.SETTLE.value
            data["tx_hash"] = tx_hash
            # come back to this skill after settling
            data["post_tx_event"] = Event.DECISION_MAKING.value

        # Reset
        return data

    def get_mech_requests(self) -> List[Dict[str, str]]:
        """Get mech requests"""

        mech_requests = [
            asdict(
                MechMetadata(
                    nonce=str(uuid.uuid4()),
                    tool=self.params.langchain_tool_name,
                    prompt=request["prompt"],
                )
            )
            for request in self.local_state.user_requests
        ]

        # Clear pending requests
        # TODO: for multi-agent, this has to be done after this round
        self.local_state.user_requests = []

        return mech_requests

    def _build_safe_tx_hash(
        self, **kwargs: Any
    ) -> Generator[None, None, Optional[str]]:
        """Prepares and returns the safe tx hash for a multisend tx."""
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.synchronized_data.safe_contract_address,
            contract_id=str(GnosisSafeContract.contract_id),
            contract_callable="get_raw_safe_transaction_hash",
            data=TX_DATA,
            safe_tx_gas=SAFE_GAS,
            chain_id=GNOSIS_CHAIN_ID,
            **kwargs,
        )

        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                "Couldn't get safe tx hash. Expected response performative "
                f"{ContractApiMessage.Performative.STATE.value!r}, "  # type: ignore
                f"received {response_msg.performative.value!r}: {response_msg}."
            )
            return None

        tx_hash = response_msg.state.body.get("tx_hash", None)
        if tx_hash is None or len(tx_hash) != TX_HASH_LENGTH:
            self.context.logger.error(
                "Something went wrong while trying to get the buy transaction's hash. "
                f"Invalid hash {tx_hash!r} was returned."
            )
            return None

        # strip "0x" from the response hash
        return tx_hash[2:]

    def process_next_mech_response(
        self, mech_response: MechInteractionResponse
    ) -> Generator[None, None, Optional[str]]:
        """Get the call data from the mech response."""

        encoded_response = mech_response.result
        if encoded_response is None:
            self.context.logger.error(
                f"No result was returned for mech with request id {mech_response.requestId!r}."
            )
            return None

        try:
            # Decision making
            response = json.loads(encoded_response)

            self.context.logger.info(f"Mech response: {response}")

            if response["p_yes"] < 0.6 or response["confidence"] < 0.6:
                self.context.logger.info(
                    f"Response was 'NO' or there is not enough confidence on the 'YES' response"
                )
                return None

            # Transfer 1 wei to the agent
            call_data = {VALUE_KEY: 1, TO_ADDRESS_KEY: self.context.agent_address}

        except json.decoder.JSONDecodeError:
            self.context.logger.error(
                f"Could not decode the mech's {encoded_response=}."
            )
            return None

        # Security measure to limit the transaction amount
        max_transfer_value_wei = self.params.max_transfer_value_wei
        if max_transfer_value_wei and call_data[VALUE_KEY] > max_transfer_value_wei:
            self.context.logger.error(
                f"Transfer value is too high. Transfer skipped. Please adjust your max_transfer_value_wei parameter: {call_data[VALUE_KEY]} > {max_transfer_value_wei}"
            )
            return None

        mismatch = EXPECTED_CALL_DATA != frozenset(call_data.keys())
        if mismatch:
            self.context.logger.error(
                "Incorrect call data were detected in the given mech response. "
                f"Expected {EXPECTED_CALL_DATA} to be present. Received {call_data=}."
            )
            return None

        safe_tx_hash = yield from self._build_safe_tx_hash(**call_data)
        if safe_tx_hash is None:
            self.context.logger.error("Could not build the safe transaction's hash.")
            return None

        tx_hash = hash_payload_to_hex(
            safe_tx_hash,
            call_data[VALUE_KEY],
            SAFE_GAS,
            call_data[TO_ADDRESS_KEY],
            TX_DATA,
        )

        return tx_hash


class PostTxDecisionMakingBehaviour(LangchainTraderBaseBehaviour):
    """PostTxDecisionMakingBehaviour"""

    matching_round: Type[AbstractRound] = PostTxDecisionMakingRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            event = cast(str, self.synchronized_data.post_tx_event)
            sender = self.context.agent_address
            payload = PostTxDecisionMakingPayload(sender=sender, event=event)

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()


class LangchainTraderRoundBehaviour(AbstractRoundBehaviour):
    """LangchainTraderRoundBehaviour"""

    initial_behaviour_cls = DecisionMakingBehaviour
    abci_app_cls = LangchainTraderAbciApp  # type: ignore
    behaviours: Set[Type[BaseBehaviour]] = [
        DecisionMakingBehaviour,
        PostTxDecisionMakingBehaviour,
    ]
