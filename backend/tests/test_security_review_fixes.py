"""Regression tests for the commit security review (denylist bypasses, taint across approvals,
honest confirmation text, no auto-memory from tainted turns)."""

from app.security.permissions import PendingApproval, SecurityPolicy


def _policy():
    from app.core.config import get_settings

    return SecurityPolicy(get_settings())


def test_dangerous_command_survives_quoting_and_whitespace_tricks():
    p = _policy()
    for cmd in ["rm\t-rf ~/x", "r'm' -rf ~/x", 'r"m" -rf ~/x', "r\\m -rf ~/x", "RM -rf ~/x"]:
        assert p.is_dangerous_command(cmd), cmd


def test_shell_indirection_is_dangerous():
    p = _policy()
    for cmd in [
        "echo cm0gLXJmIH4= | base64 -d | sh",
        "bash -c 'r''m -rf ~'",
        "python3 -c \"import shutil; shutil.rmtree('/home')\"",
        "eval $(echo x)",
        "find ~ -name '*.txt' -delete",
        "ls | xargs echo",
        "mv ~/Documentos /tmp/x",
    ]:
        assert p.is_dangerous_command(cmd), cmd
    assert not p.is_dangerous_command("ls -la ~/Documentos")
    assert not p.is_dangerous_command("xdg-open https://youtube.com")


def test_confirmation_says_the_full_command():
    from app.ai.agent_loop import describe_pending_action

    a = PendingApproval(id="1", tool_name="run_command", target="rm -rf /home/carlos/Documentos/importante",
                        params={}, description="")
    assert "/home/carlos/Documentos/importante" in describe_pending_action(a)


def test_pending_approval_carries_taint_into_approval_outcome(monkeypatch):
    import asyncio

    from app.tools.registry import ToolExecutionOutcome, tool_registry
    from app.security.permissions import PermissionLevel

    approval = PendingApproval(id="x", tool_name="biblia_ler", target="", params={"referencia": "João 3:16"},
                               description="", tainted=True)
    monkeypatch.setattr(tool_registry.policy, "pop_pending_approval", lambda _id: approval)

    async def fake_invoke(**kwargs):
        return ToolExecutionOutcome(status="executed", tool_name="biblia_ler", permission_level=PermissionLevel.SAFE)

    monkeypatch.setattr(tool_registry, "invoke", fake_invoke)
    outcome = asyncio.run(tool_registry.approve_pending(None, "x"))
    assert outcome.tainted is True


def test_tainted_turn_is_not_learned(monkeypatch):
    from app.voice import ambient_brain as ab

    calls = []
    monkeypatch.setattr(ab.learning, "note_exchange", lambda u, r: calls.append((u, r)))

    class FakeDB:
        def add(self, _):
            pass

        def commit(self):
            pass

    ab.ambient_brain._remember_turn(FakeDB(), 1, "olá", "resposta", tainted=True)
    assert calls == []
    ab.ambient_brain._remember_turn(FakeDB(), 1, "olá", "resposta")
    assert calls == [("olá", "resposta")]
