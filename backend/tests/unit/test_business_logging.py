import logging

from app.core.logging import get_business_logger


def test_business_logger_sets_business_marker(caplog):
    logger = get_business_logger("test.business")

    with caplog.at_level(logging.INFO):
        logger.info("Business event", extra={"event": "test.event"})

    assert len(caplog.records) == 1
    assert caplog.records[0].biz_marker == "BIZ"
    assert caplog.records[0].event == "test.event"
