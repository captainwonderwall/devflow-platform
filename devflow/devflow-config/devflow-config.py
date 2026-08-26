#!/usr/bin/env python3
from devflow_sdk.config.wizard import run_wizard
from devflow_sdk.config.wizard.global_steps import ModelsStep, ProviderStep
from devflow_sdk.config.wizard.tools import ALL_TOOL_STEPS


def main():
    steps = [ProviderStep(), ModelsStep()] + ALL_TOOL_STEPS
    run_wizard(steps)
    print("\nConfig saved to ~/.devflow/config.json")


if __name__ == "__main__":
    main()
