import io
import logging
import time

from vectormaps.progress import CLEAR, ProgressHandler, Spinner


class Tty(io.StringIO):
    def isatty(self):
        return True


def test_no_spinner_without_a_terminal():
    out = io.StringIO()
    with Spinner("working", stream=out):
        time.sleep(0.05)
    assert out.getvalue() == ""


def test_spinner_draws_and_cleans_up():
    out = Tty()
    with Spinner("working", stream=out, interval=0.01):
        time.sleep(0.1)
    text = out.getvalue()
    assert "working (0s)" in text
    assert text.endswith(CLEAR)  # the line is left clean for what comes next


def test_log_lines_do_not_mix_with_the_spinner():
    out = Tty()
    handler = ProgressHandler(out)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("test-progress")
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.INFO)
    with Spinner("working", stream=out, interval=0.01):
        time.sleep(0.05)
        logger.warning("hello")
    assert f"{CLEAR}hello\n" in out.getvalue()
