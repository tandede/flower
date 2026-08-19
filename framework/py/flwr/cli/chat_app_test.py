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
"""Tests for the CLI `chat` application."""


from unittest.mock import Mock, patch

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from flwr.cli.chat_app import ChatApplication, _ChatCompleter, _MarkdownBlock
from flwr.proto.federation_pb2 import Federation  # pylint: disable=E0611


def test_chat_completes_history_and_federation() -> None:
    """History and federation selection should produce completions."""
    federations = [
        Federation(name="@flower/one", description="First"),
        Federation(name="@flower/two", description="Second"),
    ]
    completer = _ChatCompleter(Mock(), None, federations)

    history = list(completer.get_completions(Document("/hist"), CompleteEvent()))
    federation_command = list(
        completer.get_completions(Document("/fed"), CompleteEvent())
    )
    federations = list(
        completer.get_completions(Document("/federation @flower/t"), CompleteEvent())
    )

    assert [completion.text for completion in history] == ["/history"]
    assert [completion.text for completion in federation_command] == ["/federation"]
    assert [completion.text for completion in federations] == ["@flower/two"]


def test_chat_federation_command_opens_dropdown() -> None:
    """The bare federation command should open the federation completion menu."""
    application = Mock()
    with patch.object(ChatApplication, "_create_application", return_value=application):
        chat = ChatApplication(Mock(), [Federation(name="@flower/workspace")], Mock())
    chat.input_buffer = Mock()
    event = Mock(app=application)

    handled = chat._handle_command(event, "/federation")

    assert handled
    assert chat.input_buffer.text == "/federation "
    assert chat.input_buffer.cursor_position == len("/federation ")
    chat.input_buffer.start_completion.assert_called_once_with(select_first=False)
    application.invalidate.assert_called_once_with()


def test_chat_new_clears_transcript() -> None:
    """Starting a new conversation should clear the viewport."""
    application = Mock()
    with patch.object(ChatApplication, "_create_application", return_value=application):
        chat = ChatApplication(Mock(), [Federation(name="@flower/workspace")], Mock())
    chat.series_id = 123
    chat.transcript = [("", "Previous conversation\n\n")]

    handled = chat._handle_command(Mock(), "/new")

    assert handled
    assert chat.series_id is None
    assert chat.transcript == []
    assert chat.follow_transcript
    application.invalidate.assert_called_once_with()


def test_chat_selects_federation() -> None:
    """Selecting a federation should start a new conversation in that context."""
    federations = [
        Federation(name="@flower/workspace"),
        Federation(name="@flower/other"),
    ]
    with patch.object(ChatApplication, "_create_application", return_value=Mock()):
        chat = ChatApplication(Mock(), federations, Mock())
    chat.series_id = 123
    chat.completer.agents = [Mock()]

    handled = chat._handle_command(Mock(), "/federation @flower/other")

    assert handled
    assert chat.federation == "@flower/other"
    assert chat.completer.federation == "@flower/other"
    assert chat.completer.agents is None
    assert chat.series_id is None
    assert chat.transcript == [
        (
            "class:notice",
            "Federation changed to @flower/other. "
            "Your next message will start a fresh conversation.\n\n",
        )
    ]


def test_chat_rejects_unknown_federation() -> None:
    """An unknown federation should leave the current conversation unchanged."""
    with patch.object(ChatApplication, "_create_application", return_value=Mock()):
        chat = ChatApplication(Mock(), [Federation(name="@flower/workspace")], Mock())
    chat.series_id = 123

    handled = chat._handle_command(Mock(), "/federation @flower/unknown")

    assert handled
    assert chat.federation == "@flower/flower-agent-execution"
    assert chat.series_id == 123
    assert chat.transcript == [
        ("class:error", "Unknown federation: @flower/unknown\n\n")
    ]


def test_chat_streams_and_renders_one_markdown_block() -> None:
    """Assistant deltas should form one styled Markdown transcript block."""
    with patch.object(ChatApplication, "_create_application", return_value=Mock()):
        chat = ChatApplication(Mock(), [Federation(name="@flower/workspace")], Mock())

    block = chat._append_markdown_delta(  # pylint: disable=protected-access
        None, "Hello **bo"
    )
    block = chat._append_markdown_delta(  # pylint: disable=protected-access
        block, "ld** and `code`."
    )
    fragments = chat._render_markdown_block(  # pylint: disable=protected-access
        block, 60
    )

    assert chat.transcript == [_MarkdownBlock("Hello **bold** and `code`.")]
    assert "**" not in "".join(text for _, text, *_ in fragments)
    assert any(text == "bold" and "bold" in style for style, text, *_ in fragments)
    assert any(text == "code" and "bg:" in style for style, text, *_ in fragments)
