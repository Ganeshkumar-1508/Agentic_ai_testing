"""Skill evolution system — track, evolve, validate, and version skills.

Components:
  - SessionTracker: records skill usage with outcomes per session
  - SkillEvolver: analyzes session data, generates improved skill candidates
  - SkillValidator: tests candidate skills against prompts
  - VersionTracker: git-based version history per skill
"""
