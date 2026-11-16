"""Offline, deterministic 1-ISIN entry-read rehearsal, without a market signal.

Synthetic planning is injected ONLY into in-memory fake state. Never connects to
Bob production, never invents broker quotes or initiates Android/DEGIRO orders.
Exercises the exact planner -> authenticated remote command -> ACK -> original
receipt correlation used for a genuine entry read, within bounded deadlines.
A real Samsung read is still a separate acceptance test.
"""
import copy
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import android_remote as remote
import handset_entry_request as entry
from test_android_remote import value, NOW
from test_handset_entry_request import Db, planning, LIST, ISIN


def owner_started_entry_session():
    message = value()
    message["purpose"] = "entry_read"
    state, response = remote.exchange({}, message, NOW)
    assert response["command"] is None
    return state, message


class SyntheticEntrySignalScenario(unittest.TestCase):
    def test_fake_confirmed_signal_exercises_one_real_reader_command_and_receipt_contract(self):
        state, message = owner_started_entry_session()
        database = Db(state)
        with patch("handset_planning.read", return_value=planning()):
            entry.prepare(database, "owner", state, NOW)
        self.assertEqual(state["entryReadStatus"], "REQUEST_QUEUED")
        self.assertEqual(len(state["commands"]), 1)
        request = state["entryRead"]
        self.assertEqual(request["isin"], ISIN)
        self.assertFalse(request["entryApproved"])
        self.assertFalse(request["brokerExecutionVerified"])

        state, delivered = remote.exchange(state, message, NOW + 1)
        command = delivered["command"]
        self.assertEqual(command["action"], "entry_read")
        self.assertEqual(command["isin"], ISIN)
        self.assertEqual(command["listBatchId"], LIST)
        self.assertEqual(command["requestId"], request["requestId"])
        self.assertLessEqual(command["expiresAt"], NOW + 21)

        ack_message = copy.deepcopy(message)
        ack_message["ack"] = {"requestId": request["requestId"],
                              "code": "ENTRY_READ_STARTED"}
        state, reply = remote.exchange(state, ack_message, NOW + 2)
        self.assertEqual(state["commands"][0]["status"], "acknowledged")
        self.assertEqual(reply["command"], None)
        database.state = state
        with patch("handset_planning.read", return_value=planning()):
            entry.prepare(database, "owner", state, NOW + 2)
        self.assertEqual(state["entryReadStatus"], "awaiting-read-receipt")

        # The device's ordinary reader returned ONE fresh observation; it did
        # not prove broker timestamp, tradability or an executed entry.
        database.run = {"results": [{"code": "COMPLETE", "observation": {
            "observedAt": datetime.fromtimestamp(NOW + 4, timezone.utc).isoformat(),
            "sourceTime": None
        }}]}
        run = {"batchId": request["requestId"], "revision": 1,
               "isins": [ISIN], "requestedFields": {ISIN: entry.FIELDS}}
        with patch("handset_planning.read", return_value=planning()):
            entry.receipt(database, "owner", LIST, run, NOW + 5)
        self.assertIsNotNone(database.saved)
        self.assertEqual(database.saved["entryReadStatus"],
                         "read-received-source-time-unverified")
        self.assertEqual(database.saved["entryRead"]["status"],
                         "read-received-source-time-unverified")
        self.assertFalse(database.saved["entryRead"]["entryApproved"])
        self.assertFalse(database.saved["entryRead"]["brokerExecutionVerified"])
        self.assertEqual(len(database.saved["commands"]), 1)

    def test_locked_samsung_cannot_receive_fake_entry_command(self):
        state, message = owner_started_entry_session()
        with patch("handset_planning.read", return_value=planning()):
            entry.prepare(Db(state), "owner", state, NOW)
        self.assertEqual(state["entryReadStatus"], "REQUEST_QUEUED")
        locked = copy.deepcopy(message)
        locked["observation"]["code"] = "WAITING_FOR_UNLOCK"
        state, response = remote.exchange(state, locked, NOW + 1)
        self.assertIsNone(response["command"])
        self.assertEqual(state["commands"][0]["status"], "queued")
        # Unlock is an owner's Android action, not a simulated PIN bypass.
        state, response = remote.exchange(state, message, NOW + 2)
        self.assertEqual(response["command"]["action"], "entry_read")

    def test_no_signal_unowned_list_and_wrong_session_must_not_start_read(self):
        no_signal, _ = owner_started_entry_session()
        plan = planning()
        plan["result"]["items"][0]["entrySuitable"] = False
        with patch("handset_planning.read", return_value=plan):
            entry.prepare(Db(no_signal), "owner", no_signal, NOW)
        self.assertFalse(no_signal["commands"])
        self.assertEqual(no_signal["entryReadStatus"], "WAITING_FOR_SIGNAL")

        wrong_list, _ = owner_started_entry_session()
        foreign = Db(wrong_list)
        foreign.listAt = "different-list"
        with patch("handset_planning.read", return_value=planning()):
            entry.prepare(foreign, "owner", wrong_list, NOW)
        self.assertFalse(wrong_list["commands"])
        self.assertEqual(wrong_list["entryReadStatus"], "OWNED_CURRENT_LIST_REQUIRED")

        normal = remote.exchange({}, value(), NOW)[0]
        with patch("handset_planning.read", side_effect=AssertionError(
                "non-entry session must not request planning")):
            entry.prepare(Db(normal), "owner", normal, NOW)
        self.assertFalse(normal["commands"])
        self.assertNotIn("entryRead", normal)

    def test_rehearsal_ack_is_not_completion_and_expiry_never_replays(self):
        state, message = owner_started_entry_session()
        with patch("handset_planning.read", return_value=planning()):
            entry.prepare(Db(state), "owner", state, NOW)
        state, delivered = remote.exchange(state, message, NOW + 1)
        request = state["entryRead"]
        ack = copy.deepcopy(message)
        ack["ack"] = {"requestId": request["requestId"],
                      "code": "ENTRY_READ_STARTED"}
        state, _ = remote.exchange(state, ack, NOW + 2)
        with patch("handset_planning.read", return_value=planning()):
            entry.prepare(Db(state), "owner", state, NOW + 3)
        self.assertEqual(state["entryReadStatus"], "awaiting-read-receipt")
        entry.prepare(Db(state), "owner", state, NOW + 181)
        self.assertEqual(state["entryReadStatus"], "expired")
        self.assertEqual(len(state["commands"]), 1)
        self.assertFalse(state["entryRead"]["entryApproved"])
        self.assertFalse(state["entryRead"]["brokerExecutionVerified"])


if __name__ == "__main__":
    unittest.main()
