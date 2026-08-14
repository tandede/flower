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

from flwr.cli.chat_app import ChatApplication, _ChatCommandCompleter
from flwr.proto.federation_pb2 import Federation  # pylint: disable=E0611


def test_chat_completes_history_but_not_federation() -> None:
    """Only the enabled history command should be completed."""
    completer = _ChatCommandCompleter()

    history = list(completer.get_completions(Document("/hist"), CompleteEvent()))
    federation = list(
        completer.get_completions(Document("/federation"), CompleteEvent())
    )

    assert [completion.text for completion in history] == ["/history"]
    assert federation == []


def test_chat_always_uses_default_federation() -> None:
    """Chat should use the default federation and reject federation changes."""
    with patch.object(ChatApplication, "_create_application", return_value=Mock()):
        chat = ChatApplication(Mock(), [Federation(name="@flower/workspace")])
    chat.series_id = 123

    handled = chat._handle_command(Mock(), "/federation @flower/default")

    assert handled
    assert chat.federation == "@flower/flower-agent-execution"
    assert chat.series_id == 123
    assert chat.transcript == [
        ("class:notice", "/federation is currently disabled.\n\n")
    ]
