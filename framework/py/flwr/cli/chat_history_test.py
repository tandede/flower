# Copyright 2026 Flower Labs GmbH. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Tests for conversation history in the CLI `chat` application."""


from unittest.mock import Mock, patch

from prompt_toolkit.utils import get_cwidth

from flwr.cli.chat_app import ChatApplication
from flwr.proto.control_pb2 import ListRunSeriesRequest, ListRunSeriesResponse
from flwr.proto.federation_pb2 import Federation  # pylint: disable=E0611
from flwr.proto.runseries_pb2 import RunSeries  # pylint: disable=E0611


def _create_chat(stub: Mock) -> ChatApplication:
    with patch.object(ChatApplication, "_create_application", return_value=Mock()):
        return ChatApplication(
            stub,
            [Federation(name="@flower/flower-agent-execution")],
        )


def test_history_lists_compact_chronological_rows() -> None:
    """History should render oldest first and highlight the latest compact row."""
    stub = Mock()
    stub.ListRunSeries.return_value = ListRunSeriesResponse(
        entries=[
            RunSeries(series_id=7, description="Latest conversation " * 20),
            RunSeries(series_id=12345, description="Older"),
        ]
    )
    chat = _create_chat(stub)

    assert chat._handle_command(Mock(), "/history")  # pylint: disable=protected-access

    stub.ListRunSeries.assert_called_once_with(
        ListRunSeriesRequest(federation_id="@flower/flower-agent-execution")
    )
    assert chat.history_block is not None
    assert [entry.series_id for entry in chat.history_block.entries] == [12345, 7]
    assert chat.history_block.selected_index == 1
    fragments = chat._render_history_block(  # pylint: disable=protected-access
        chat.history_block, 60
    )
    rows = [
        text.removesuffix("\n")
        for style, text, *_ in fragments
        if style in {"", "class:history.selected"}
    ]
    assert rows[0].index("Older") == rows[1].index("Latest")
    assert get_cwidth(rows[1]) == 60
    assert rows[1].endswith("…")


def test_history_navigation_tracks_and_confirms_selection() -> None:
    """Moving the selection should scroll to it and Enter should continue it."""
    stub = Mock()
    stub.ListRunSeries.return_value = ListRunSeriesResponse(
        entries=[
            RunSeries(series_id=3, description="Latest"),
            RunSeries(series_id=2, description="Middle"),
            RunSeries(series_id=1, description="Oldest"),
        ]
    )
    chat = _create_chat(stub)
    chat._handle_command(Mock(), "/history")  # pylint: disable=protected-access
    assert chat.history_block is not None
    chat.wrapped_transcript = (
        chat._render_history_block(  # pylint: disable=protected-access
            chat.history_block, 100
        )
    )
    latest_cursor = chat._transcript_cursor()  # pylint: disable=protected-access

    chat._move_history_selection(-1)  # pylint: disable=protected-access
    chat._move_history_selection(-1)  # pylint: disable=protected-access
    chat.wrapped_transcript = (
        chat._render_history_block(  # pylint: disable=protected-access
            chat.history_block, 100
        )
    )
    oldest_cursor = chat._transcript_cursor()  # pylint: disable=protected-access
    chat._confirm_history_selection()  # pylint: disable=protected-access

    assert latest_cursor.y > oldest_cursor.y
    assert chat.history_block is None
    assert chat.series_id == 1
    assert chat.transcript == [("class:notice", "Continuing conversation 1.\n\n")]


def test_history_handles_empty_result() -> None:
    """An empty history should produce a clear message."""
    stub = Mock()
    stub.ListRunSeries.return_value = ListRunSeriesResponse()
    chat = _create_chat(stub)

    chat._handle_command(Mock(), "/history")  # pylint: disable=protected-access

    assert chat.history_block is None
    assert chat.transcript == [
        (
            "class:notice",
            "No conversation history found for @flower/flower-agent-execution.\n\n",
        )
    ]
