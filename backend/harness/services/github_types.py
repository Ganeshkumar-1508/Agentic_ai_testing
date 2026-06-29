"""GitHub service types — ported from OpenHands enterprise integration."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ProviderType(str, Enum):
    GITHUB = "github"
    GITLAB = "gitlab"


class OwnerType(str, Enum):
    USER = "user"
    ORGANIZATION = "organization"


@dataclass
class Repository:
    id: str
    full_name: str
    git_provider: ProviderType
    is_public: bool
    stargazers_count: int | None = None
    pushed_at: str | None = None
    owner_type: OwnerType | None = None
    main_branch: str | None = None


@dataclass
class Branch:
    name: str
    commit_sha: str
    protected: bool
    last_push_date: str | None = None


@dataclass
class PaginatedBranches:
    branches: list[Branch]
    has_next_page: bool
    current_page: int
    per_page: int
    total_count: int | None = None


@dataclass
class PullRequest:
    number: int
    title: str
    body: str
    state: str
    head_sha: str
    base_ref: str
    head_ref: str
    author: str | None = None
    merged: bool = False
    mergeable: bool | None = None
    labels: list[str] = field(default_factory=list)


@dataclass
class RepoAccess:
    """What the user's token gives access to."""
    repos: list[Repository]
    has_write: bool = False
