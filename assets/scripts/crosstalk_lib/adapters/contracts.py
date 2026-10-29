"""Small immutable contracts at the CLI/terminal boundary."""
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Mapping
from types import MappingProxyType


@dataclass(frozen=True)
class SurfaceRef:
    backend: str
    native_id: str

    def __post_init__(self):
        patterns = {'ghostty': r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',
                    'cmux': r'(?:surface:[0-9]+|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})'}
        if self.backend not in patterns or not re.fullmatch(patterns[self.backend], self.native_id):
            raise ValueError('Invalid exact terminal surface')

    @classmethod
    def parse(cls, value):
        if value.startswith('ghostty:'):
            return cls('ghostty', value.removeprefix('ghostty:'))
        if value.startswith('cmux:'):
            return cls('cmux', value.removeprefix('cmux:'))
        return cls('cmux', value)

    def address(self):
        return 'ghostty:' + self.native_id if self.backend == 'ghostty' else self.native_id


@dataclass(frozen=True)
class LaunchSpec:
    executable: str
    argv: tuple[str, ...]
    cwd: str
    env_delta: Mapping[str, str]
    bootstrap_instruction: str
    permission_mode: str = 'default'
    timeout_policy: str = 'startup'

    def __post_init__(self):
        if any(not isinstance(value, str) or '\0' in value for value in (self.executable, self.cwd, self.bootstrap_instruction)):
            raise ValueError('Launch fields must be literal strings')
        if not Path(self.executable).is_absolute() or not Path(self.cwd).is_absolute():
            raise ValueError('Launch paths must be absolute')
        if not isinstance(self.argv, tuple) or any(not isinstance(arg, str) or '\0' in arg for arg in self.argv):
            raise ValueError('Launch argv must be literal strings')
        if self.permission_mode not in ('default', 'auto-approve') or self.timeout_policy != 'startup':
            raise ValueError('Unsupported launch policy')
        allowed = {'PATH', 'CROSSTALK_CONFIG_DIR'}
        if set(self.env_delta) != allowed or any(not isinstance(value, str) or '\0' in value for value in self.env_delta.values()):
            raise ValueError('Unsupported launch environment changes')
        if not Path(self.env_delta['CROSSTALK_CONFIG_DIR']).is_absolute():
            raise ValueError('State directory must be absolute')
        object.__setattr__(self, 'env_delta', MappingProxyType(dict(self.env_delta)))


@dataclass(frozen=True)
class CapabilitySet:
    features: Mapping[str, str]
    observed_at: str
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if any(value not in ('supported', 'unsupported', 'unknown') for value in self.features.values()):
            raise ValueError('Invalid capability state')
        object.__setattr__(self, 'features', MappingProxyType(dict(self.features)))

    def require(self, *names):
        if any(self.features.get(name, 'unknown') != 'supported' for name in names):
            raise ValueError('Required capability is unsupported or unknown')


@dataclass(frozen=True)
class SubmissionOutcome:
    state: str
    error_code: str | None = None

    def __post_init__(self):
        if self.state not in ('submitted', 'failed', 'unknown'):
            raise ValueError('Invalid submission outcome')
