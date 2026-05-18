"""ASMR Seamless Loop Maker.

A toolkit that turns a short clip into a long, seamlessly looping ASMR video
with smooth visual and audio transitions.
"""

from asmr_loop_maker.analyzer import LoopAnalysis, analyze_video
from asmr_loop_maker.processor import ProcessResult, process_video
from asmr_loop_maker.batch import BatchResult, process_batch

__all__ = [
    "LoopAnalysis",
    "analyze_video",
    "ProcessResult",
    "process_video",
    "BatchResult",
    "process_batch",
]

__version__ = "0.1.0"
