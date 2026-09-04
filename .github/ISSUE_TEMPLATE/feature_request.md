name: Feature Request
description: Propose a new feature or enhancement for RoadResQ
title: "[FEATURE] "
labels: ["enhancement"]
assignees: ""
body:
  - type: markdown
    attributes:
      value: |
        Propose a new capability or architectural enhancement for RoadResQ.
  - type: textarea
    id: problem
    attributes:
      label: Problem Statement
      description: Is your feature request related to a problem or user need?
    validations:
      required: true
  - type: textarea
    id: proposed_solution
    attributes:
      label: Proposed Solution
      description: Describe the solution or feature you'd like to see implemented.
    validations:
      required: true
  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives Considered
      description: Any alternative solutions or features you've considered.
    validations:
      required: false
