from setuptools import find_packages, setup

setup(
    name="agent-terminal-bridge",
    version="0.1.0",
    description="Local iTerm2 lifecycle status for coding agents",
    packages=find_packages("src"),
    package_dir={"": "src"},
    python_requires=">=3.9",
    entry_points={"console_scripts": [
        "agent-terminal-bridge=agent_terminal_bridge.cli:main",
        "aiterm=agent_terminal_bridge.cli:main",
    ]},
)
