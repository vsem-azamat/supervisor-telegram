"""Unit tests for app.channel.exceptions."""

from app.channel.exceptions import (
    ChannelPipelineError,
    ImagePipelineError,
)


def test_image_pipeline_error_inherits_from_channel_pipeline_error():
    exc = ImagePipelineError("boom")
    assert isinstance(exc, ChannelPipelineError)
    assert isinstance(exc, Exception)
    assert str(exc) == "boom"
