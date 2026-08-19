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


import json
from unittest.mock import Mock, patch

from prompt_toolkit.utils import get_cwidth

from flwr.app import ConfigRecord, Context, RecordDict
from flwr.cli.chat_app import ChatApplication, _MarkdownBlock
from flwr.common.serde import context_to_proto
from flwr.proto.control_pb2 import (
    GetRunSeriesRequest,
    GetRunSeriesResponse,
    ListRunSeriesRequest,
    ListRunSeriesResponse,
)
from flwr.proto.federation_pb2 import Federation  # pylint: disable=E0611
from flwr.proto.runseries_pb2 import RunSeries  # pylint: disable=E0611


def _create_chat(stub: Mock) -> ChatApplication:
    with patch.object(ChatApplication, "_create_application", return_value=Mock()):
        return ChatApplication(
            stub,
            [Federation(name="@flower/flower-agent-execution")],
            Mock(),
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
    stub.GetRunSeries.return_value = GetRunSeriesResponse(
        series=RunSeries(
            series_id=1,
            federation="@flower/flower-agent-execution",
        )
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
    assert chat.transcript == []


def test_history_selection_restores_conversation_context() -> None:
    """Selecting history should replace the transcript with its saved messages."""
    stub = Mock()
    series = RunSeries(
        series_id=7,
        federation="@flower/flower-agent-execution",
        description="Saved conversation",
    )
    stub.ListRunSeries.return_value = ListRunSeriesResponse(entries=[series])
    context = Context(
        run_id=10,
        node_id=0,
        node_config={},
        state=RecordDict(
            {
                "items": ConfigRecord(
                    {
                        "json": [
                            json.dumps(
                                {
                                    "type": "message",
                                    "role": "user",
                                    "content": "Previous question",
                                }
                            ),
                            json.dumps(
                                {
                                    "type": "message",
                                    "role": "assistant",
                                    "content": [
                                        {
                                            "type": "output_text",
                                            "text": "Previous answer",
                                        }
                                    ],
                                }
                            ),
                            json.dumps({"type": "function_call", "name": "search"}),
                            "invalid JSON",
                        ]
                    }
                )
            }
        ),
        run_config={},
        series_id=7,
    )
    stub.GetRunSeries.return_value = GetRunSeriesResponse(
        series=series,
        context=context_to_proto(context),
    )
    chat = _create_chat(stub)
    chat.transcript = [("", "Current conversation\n\n")]
    chat._handle_command(Mock(), "/history")  # pylint: disable=protected-access

    chat._confirm_history_selection()  # pylint: disable=protected-access

    stub.GetRunSeries.assert_called_once_with(GetRunSeriesRequest(series_id=7))
    assert chat.series_id == 7
    assert chat.transcript == [
        ("class:user.message", "❯ Previous question\n"),
        ("", "\n"),
        _MarkdownBlock("Previous answer"),
    ]


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
