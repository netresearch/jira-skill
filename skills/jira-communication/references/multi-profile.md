# Multi-Profile Configuration

Manage connections to multiple Jira instances via `~/.jira/profiles.json`.

## Profile Resolution Priority

When a script runs, it resolves which profile to use in this order:

1. **Explicit `--profile` flag** — `--profile myprofile` selects the named profile directly
2. **Full Jira URL** — matches the URL's host against each profile's `url` field (normalized, port-insensitive)
3. **Issue key prefix** — matches the project prefix (e.g. `WEB` from `WEB-1381`) against each profile's `projects` list
4. **`.jira-profile` file** — reads the profile name from a `.jira-profile` file in the current working directory
5. **Default profile** — uses the `default` key from `profiles.json`

If none of the above match, the script raises an error listing available profiles.

## `--profile` Flag

All scripts accept `--profile` (or `-P`) to select a profile explicitly:

```bash
uv run scripts/core/jira-issue.py --profile cloud get WEB-123
uv run scripts/core/jira-search.py --profile server query "project = OPS"
```

## `~/.jira/profiles.json` Format

```json
{
  "default": "cloud",
  "profiles": {
    "cloud": {
      "url": "https://yourcompany.atlassian.net",
      "auth": "cloud",
      "username": "user@example.com",
      "api_token": "your-cloud-api-token",
      "projects": ["WEB", "MOBILE", "API"]
    },
    "server": {
      "url": "https://jira.yourcompany.com",
      "auth": "pat",
      "token": "your-personal-access-token",
      "projects": ["OPS", "INFRA", "SRVMO"]
    }
  }
}
```

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| `url` | Always | Jira instance URL |
| `auth` | No | `"cloud"` or `"pat"` (default: `"pat"`) |
| `token` | If `auth: "pat"` | Personal access token (Server/DC) |
| `username` | If `auth: "cloud"` | Atlassian account email |
| `api_token` | If `auth: "cloud"` | Atlassian API token |
| `projects` | No | List of project prefixes for auto-resolution from issue keys |

### Top-Level Keys

| Key | Description |
|-----|-------------|
| `default` | Name of the default profile (used as fallback) |
| `profiles` | Object mapping profile names to their configuration |

## `.jira-profile` File

Place a `.jira-profile` file in a project directory to set the default profile for that project:

```bash
echo "server" > /path/to/my-project/.jira-profile
```

When you run a script from that directory without `--profile` and without an issue key match, the profile named in `.jira-profile` is used.

## Auto-Resolution from Issue Key

When you reference an issue like `WEB-123`, the script extracts the project prefix `WEB` and checks each profile's `projects` list. If exactly one profile lists `WEB`, that profile is selected automatically.

If multiple profiles claim the same project prefix, the script raises an error asking you to disambiguate with `--profile`.

## Migration and Management

- **`--migrate`**: Use `jira-setup.py --migrate` to convert an existing `~/.env.jira` file into a profile in `~/.jira/profiles.json`.
- **`--all-profiles`**: Use `jira-validate.py --all-profiles` to validate all configured profiles at once.

## Fallback Behavior

If `~/.jira/profiles.json` does not exist, scripts fall back to the legacy `~/.env.jira` file and environment variables. The `--profile` flag requires `profiles.json` to exist.
