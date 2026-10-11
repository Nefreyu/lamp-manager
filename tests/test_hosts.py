from services.hosts import MARKER, add_entry, has_entry, remove_entry

SYSTEM = (
    "127.0.0.1\tlocalhost\n"
    "127.0.1.1\tjuan-pc\n"
    "\n"
    "# The following lines are desirable for IPv6 capable hosts\n"
    "::1     ip6-localhost ip6-loopback\n"
)


def managed(domain: str) -> str:
    return f"127.0.0.1\t{domain}\t{MARKER}\n"


def test_add_entry_appends_managed_line():
    result = add_entry(SYSTEM, "demo.test")
    assert result == SYSTEM + managed("demo.test")


def test_add_entry_is_idempotent():
    once = add_entry(SYSTEM, "demo.test")
    assert add_entry(once, "demo.test") == once


def test_add_entry_ignores_substring_of_other_domain():
    content = SYSTEM + managed("symfony-demo.test")
    result = add_entry(content, "demo.test")
    assert result == content + managed("demo.test")


def test_add_entry_respects_manual_entry():
    content = SYSTEM + "127.0.0.1 demo.test\n"
    assert add_entry(content, "demo.test") == content


def test_add_entry_is_case_insensitive():
    content = SYSTEM + managed("CalendarioDeTareas.test")
    assert add_entry(content, "calendariodetareas.test") == content


def test_add_entry_without_trailing_newline():
    assert add_entry("127.0.0.1 localhost", "demo.test") == "127.0.0.1 localhost\n" + managed("demo.test")


def test_add_entry_on_empty_file():
    assert add_entry("", "demo.test") == managed("demo.test")


def test_has_entry_ignores_comments():
    assert not has_entry("# 127.0.0.1 demo.test\n", "demo.test")
    assert not has_entry("127.0.0.1 localhost # demo.test\n", "demo.test")


def test_remove_entry_keeps_domain_containing_it():
    content = SYSTEM + managed("symfony-demo.test") + managed("demo.test")
    assert remove_entry(content, "demo.test") == SYSTEM + managed("symfony-demo.test")


def test_remove_entry_never_touches_manual_lines():
    content = SYSTEM + "127.0.0.1 demo.test\n"
    assert remove_entry(content, "demo.test") == content


def test_remove_entry_keeps_system_lines_and_comments():
    content = SYSTEM + managed("demo.test")
    assert remove_entry(content, "demo.test") == SYSTEM


def test_remove_entry_missing_domain_returns_same_content():
    content = SYSTEM + managed("other.test")
    assert remove_entry(content, "demo.test") == content


def test_remove_entry_is_case_insensitive():
    content = SYSTEM + managed("SymfonyUXDemo.test")
    assert remove_entry(content, "symfonyuxdemo.test") == SYSTEM


def test_remove_entry_from_managed_line_with_several_hosts():
    content = SYSTEM + f"127.0.0.1\tdemo.test api.demo.test\t{MARKER}\n"
    assert remove_entry(content, "demo.test") == SYSTEM + managed("api.demo.test")


def test_remove_entry_last_line_without_newline():
    content = SYSTEM + managed("other.test") + f"127.0.0.1\tdemo.test\t{MARKER}"
    assert remove_entry(content, "demo.test") == SYSTEM + managed("other.test")
