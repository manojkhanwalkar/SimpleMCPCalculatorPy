# SimpleMCPCalculatorPy

A Python port of [SimpleMCPCalculator](https://github.com/manojkhanwalkar/SimpleMCPCalculator) (converted from commit `6794f98`). It has two [MCP](https://modelcontextprotocol.io) calculator servers, a basic one and a scientific one, and three command-line clients that launch them and call their tools over stdio. The port aims to be a drop-in replacement: the same tools, results, error texts and command-line behaviour as the Java original.

Work in progress: the code arrives through pull requests.

## Open in IntelliJ IDEA

Run `uv sync` once, then *File → Open* this folder. IntelliJ needs the Python plugin. The first time, it asks for an interpreter: choose *Add interpreter → Existing → `.venv/bin/python`* and name it `uv (SimpleMCPCalculatorPy)`, the name the project files refer to.
