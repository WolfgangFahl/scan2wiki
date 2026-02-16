# AGENTS.md - Development Guide for AI Coding Agents

This guide provides essential information for AI coding agents working with the Scan2Wiki codebase.

## Build/Lint/Test Commands

### Installation
```bash
# Install dependencies
./scripts/install

# Or install in development mode
pip install -e .
```

### Running Tests
```bash
# Run all tests
./scripts/test

# Run tests with green (recommended)
./scripts/test --green

# Run tests module by module
./scripts/test --module

# Run a single test file
python -m unittest tests.test_barcode

# Run a specific test method
python -m unittest tests.test_barcode.TestBarcode.test_barcodes
```

### Code Formatting
```bash
# Format code with black and isort
./scripts/blackisort
```

### Documentation
```bash
# Generate documentation
./scripts/doc
```

## Code Style Guidelines

### Imports
- Use absolute imports when possible
- Group imports in the order: standard library, third-party, local
- Use isort for import organization
- Avoid wildcard imports

### Formatting
- Use Black for code formatting with default settings (line length 88)
- Use isort for import sorting
- Follow PEP 8 style guidelines
- Use 4 spaces for indentation (no tabs)

### Types
- Use type hints for function parameters and return values
- Use dataclasses where appropriate
- Leverage dataclasses-json for serialization needs

### Naming Conventions
- Use snake_case for variables and functions
- Use PascalCase for classes
- Use UPPER_CASE for constants
- Use descriptive names that convey purpose

### Error Handling
- Use specific exception types rather than generic `Exception`
- Provide meaningful error messages
- Log errors appropriately using the project's logging system
- Use try/except blocks judiciously

### Documentation
- Write docstrings in Google style or NumPy style
- Document all public APIs
- Include examples in docstrings where helpful

## Testing

### Test Framework
- Use the `ngwidgets.basetest.Basetest` base class for tests
- Name test files as `test_*.py`
- Name test classes as `Test*`
- Name test methods as `test_*`

### Test Coverage
- Include both positive and negative test cases
- Test edge cases and error conditions
- Use the debug flag (`debug=True`) in test classes for verbose output

## Project Architecture

### Main Components
1. `scan/` - Core scanning and processing functionality
2. `tests/` - Unit tests for all functionality
3. `scripts/` - Utility scripts for development
4. `scan2wiki_examples/` - Sample data and examples

### Key Modules
- `scan/scans.py` - Main scanning functionality
- `scan/upload.py` - Document upload to MediaWiki
- `scan/barcode.py` - Barcode processing
- `scan/dms.py` - Document management system
- `scan/product.py` - Product information handling

## Development Workflow

1. Create a feature branch from main
2. Make changes following code style guidelines
3. Run formatting: `./scripts/blackisort`
4. Run tests: `./scripts/test`
5. Commit changes with descriptive messages
6. Push and create a pull request

## Dependencies

Main dependencies are specified in `pyproject.toml`:
- `pybasemkit` - Base utilities
- `ngwidgets` - NiceGUI widgets
- `py-3rdparty-mediawiki` - MediaWiki integration
- `PyMuPDF` - PDF processing
- `pyzbar` - Barcode decoding

For development, also install:
- `black` - Code formatting
- `isort` - Import sorting
- `green` - Test runner (optional)

## CI/CD

GitHub Actions workflow in `.github/workflows/build.yml`:
- Tests run on Ubuntu with Python 3.12
- Uses `./scripts/install` for setup
- Uses `./scripts/test` for running tests

## Common Tasks

### Adding a New Feature
1. Create tests in the `tests/` directory
2. Implement functionality in the `scan/` directory
3. Run tests to ensure nothing is broken
4. Format code with `./scripts/blackisort`

### Debugging
- Use the built-in logging system
- Set `debug=True` in test classes to enable verbose output
- Check the `scan/logger.py` module for logging configuration

### Adding Dependencies
1. Add to `pyproject.toml` dependencies list
2. Update installation scripts if needed
3. Test that installation works correctly

This guide should provide AI agents with all necessary information to work effectively with the Scan2Wiki codebase.