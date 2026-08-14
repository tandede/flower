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
from flwr.proto.control_pb2 import (
    GetRunSeriesRequest,
    GetRunSeriesResponse,
    ListRunSeriesRequest,
    ListRunSeriesResponse,
)
from flwr.proto.federation_pb2 import Federation  # pylint: disable=E0611
from flwr.proto.runseries_pb2 import RunSeries  # pylint: disable=E0611


def test_history_lists_series_for_selected_federation() -> None:
    """The history command should filter series by the active federation."""
    stub = Mock()
    stub.ListRunSeries.return_value = ListRunSeriesResponse(
        entries=[
            RunSeries(
                series_id=123,
                description="Summarize my issues",
            )
        ]
    )
    with patch.object(ChatApplication, "_create_application", return_value=Mock()):
        chat = ChatApplication(
            stub,
            [Federation(name="@flower/flower-agent-execution")],
        )
    assert chat._handle_command(Mock(), "/history")  # pylint: disable=protected-access

    stub.ListRunSeries.assert_called_once_with(
        ListRunSeriesRequest(federation_id="@flower/flower-agent-execution")
    )
    assert chat.history_block is not None
    assert chat.history_block.entries[0].series_id == 123
    assert chat.history_block.selected_index == 0
    fragments = chat._render_history_block(  # pylint: disable=protected-access
        chat.history_block, 100
    )
    rendered_text = "".join(fragment[1] for fragment in fragments)
    assert "❯ 123" in rendered_text
    assert "Summarize my issues" in rendered_text
    assert "Up/Down to select · Enter to continue · Esc to cancel" in rendered_text


def test_history_selects_conversation_from_default_federation() -> None:
    """Selecting a listed series should continue it on the next message."""
    stub = Mock()
    stub.GetRunSeries.return_value = GetRunSeriesResponse(
        series=RunSeries(
            series_id=123,
            federation="@flower/flower-agent-execution",
        )
    )
    with patch.object(ChatApplication, "_create_application", return_value=Mock()):
        chat = ChatApplication(
            stub,
            [Federation(name="@flower/flower-agent-execution")],
        )

    assert chat._handle_command(  # pylint: disable=protected-access
        Mock(), "/history 123"
    )

    stub.GetRunSeries.assert_called_once_with(GetRunSeriesRequest(series_id=123))
    assert chat.series_id == 123
    assert chat.transcript == [("class:notice", "Continuing conversation 123.\n\n")]


def test_history_moves_highlight_and_confirms_selection() -> None:
    """Up or Down should move the highlight and Enter should select its row."""
    stub = Mock()
    stub.ListRunSeries.return_value = ListRunSeriesResponse(
        entries=[
            RunSeries(series_id=456, description="Second"),
            RunSeries(series_id=123, description="First"),
        ]
    )
    stub.GetRunSeries.return_value = GetRunSeriesResponse(
        series=RunSeries(
            series_id=456,
            federation="@flower/flower-agent-execution",
        )
    )
    with patch.object(ChatApplication, "_create_application", return_value=Mock()):
        chat = ChatApplication(
            stub,
            [Federation(name="@flower/flower-agent-execution")],
        )

    chat._handle_command(Mock(), "/history")  # pylint: disable=protected-access

    assert chat.history_block is not None
    assert chat.history_block.selected_index == 1
    assert [entry.series_id for entry in chat.history_block.entries] == [123, 456]

    chat._move_history_selection(-1)  # pylint: disable=protected-access
    assert chat.history_block.selected_index == 0
    chat._move_history_selection(1)  # pylint: disable=protected-access
    assert chat.history_block.selected_index == 1

    chat._confirm_history_selection()  # pylint: disable=protected-access

    stub.GetRunSeries.assert_called_once_with(GetRunSeriesRequest(series_id=456))
    assert chat.history_block is None
    assert chat.series_id == 456
    assert chat.transcript == [("class:notice", "Continuing conversation 456.\n\n")]


def test_history_cursor_tracks_selected_row() -> None:
    """The transcript cursor should follow a selection outside the viewport."""
    stub = Mock()
    stub.ListRunSeries.return_value = ListRunSeriesResponse(
        entries=[
            RunSeries(series_id=3, description="Latest"),
            RunSeries(series_id=2, description="Middle"),
            RunSeries(series_id=1, description="Oldest"),
        ]
    )
    with patch.object(ChatApplication, "_create_application", return_value=Mock()):
        chat = ChatApplication(
            stub,
            [Federation(name="@flower/flower-agent-execution")],
        )
    chat._handle_command(Mock(), "/history")  # pylint: disable=protected-access
    assert chat.history_block is not None
    chat.wrapped_transcript = (
        chat._render_history_block(  # pylint: disable=protected-access
            chat.history_block, 100
        )
    )

    latest_cursor = chat._transcript_cursor()  # pylint: disable=protected-access
    chat._move_history_selection(-2)  # pylint: disable=protected-access
    chat.wrapped_transcript = (
        chat._render_history_block(  # pylint: disable=protected-access
            chat.history_block, 100
        )
    )
    oldest_cursor = chat._transcript_cursor()  # pylint: disable=protected-access

    assert latest_cursor.y > oldest_cursor.y


def test_history_truncates_long_description_to_one_row() -> None:
    """A long description should not wrap onto another visual row."""
    stub = Mock()
    stub.ListRunSeries.return_value = ListRunSeriesResponse(
        entries=[RunSeries(series_id=123, description="Long description " * 20)]
    )
    with patch.object(ChatApplication, "_create_application", return_value=Mock()):
        chat = ChatApplication(
            stub,
            [Federation(name="@flower/flower-agent-execution")],
        )
    chat._handle_command(Mock(), "/history")  # pylint: disable=protected-access
    assert chat.history_block is not None

    fragments = chat._render_history_block(  # pylint: disable=protected-access
        chat.history_block, 60
    )
    selected_row = next(
        text for style, text, *_ in fragments if style == "class:history.selected"
    ).removesuffix("\n")

    assert get_cwidth(selected_row) == 60
    assert selected_row.endswith("…")


def test_history_right_aligns_series_ids() -> None:
    """Descriptions should begin in the same column for differently sized IDs."""
    stub = Mock()
    stub.ListRunSeries.return_value = ListRunSeriesResponse(
        entries=[
            RunSeries(series_id=7, description="Latest"),
            RunSeries(series_id=12345, description="Older"),
        ]
    )
    with patch.object(ChatApplication, "_create_application", return_value=Mock()):
        chat = ChatApplication(
            stub,
            [Federation(name="@flower/flower-agent-execution")],
        )
    chat._handle_command(Mock(), "/history")  # pylint: disable=protected-access
    assert chat.history_block is not None

    fragments = chat._render_history_block(  # pylint: disable=protected-access
        chat.history_block, 80
    )
    rows = [
        text.removesuffix("\n")
        for style, text, *_ in fragments
        if style in {"", "class:history.selected"}
    ]

    assert rows[0].index("Older") == rows[1].index("Latest")
    assert "❯     7" in rows[1]


def test_history_rejects_conversation_from_another_federation() -> None:
    """A series from another federation should not become active."""
    stub = Mock()
    stub.GetRunSeries.return_value = GetRunSeriesResponse(
        series=RunSeries(series_id=123, federation="@flower/other")
    )
    with patch.object(ChatApplication, "_create_application", return_value=Mock()):
        chat = ChatApplication(
            stub,
            [Federation(name="@flower/flower-agent-execution")],
        )

    assert chat._handle_command(  # pylint: disable=protected-access
        Mock(), "/history 123"
    )

    assert chat.series_id is None
    assert chat.transcript == [
        (
            "class:error",
            "Conversation 123 does not belong to "
            "@flower/flower-agent-execution.\n\n",
        )
    ]


def test_history_handles_empty_history() -> None:
    """An empty federation history should produce a clear message."""
    stub = Mock()
    stub.ListRunSeries.return_value = ListRunSeriesResponse()
    with patch.object(ChatApplication, "_create_application", return_value=Mock()):
        chat = ChatApplication(
            stub,
            [Federation(name="@flower/flower-agent-execution")],
        )

    chat._handle_command(Mock(), "/history")  # pylint: disable=protected-access

    assert chat.history_block is None
    assert chat.transcript == [
        (
            "class:notice",
            "No conversation history found for @flower/flower-agent-execution.\n\n",
        )
    ]
