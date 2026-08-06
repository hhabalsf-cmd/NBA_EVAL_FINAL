"""Shared test configuration.

Set before any project import: the test suite never exercises the optional
TensorFlow neural path, and importing TF can deadlock restricted shells.
"""
import os

os.environ.setdefault("NBA_EVAL_DISABLE_TF", "1")
