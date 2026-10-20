"""Ensure unittest CI actually executes legacy free-function regression cases."""

import importlib
import inspect
import unittest


class TestDiscoveryContract(unittest.TestCase):
    def test_all_standalone_functions_are_collected(self):
        for module_name in ("test_observations", "test_structured"):
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                standalone = [
                    value for name, value in vars(module).items()
                    if name.startswith("test_") and inspect.isfunction(value)
                    and value.__module__ == module.__name__
                ]
                self.assertGreater(len(standalone), 0)
                suite = unittest.defaultTestLoader.loadTestsFromModule(module)
                self.assertEqual(len(standalone), suite.countTestCases())
