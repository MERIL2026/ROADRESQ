name: Bug Report
description: Create a report to help us fix a bug or issue in RoadResQ
title: "[BUG] "
labels: ["bug"]
assignees: ""
body:
  - type: markdown
    attributes:
      value: |
        Thank you for reporting an issue! Please fill out the sections below.
  - type: textarea
    id: summary
    attributes:
      label: Bug Summary
      description: Concise description of what went wrong.
    validations:
      required: true
  - type: textarea
    id: reproduce
    attributes:
      label: Steps to Reproduce
      description: Step by step instructions to reproduce the behavior.
      placeholder: |
        1. Go to '...'
        2. Click on '....'
        3. See error
    validations:
      required: true
  - type: textarea
    id: expected
    attributes:
      label: Expected Behavior
      description: What you expected to happen.
    validations:
      required: true
  - type: textarea
    id: environment
    attributes:
      label: Environment & Tools
      description: Operating System, Docker version, Python/Node version.
      placeholder: Windows 11 / WSL2, Docker 25.0, Python 3.12
    validations:
      required: false
