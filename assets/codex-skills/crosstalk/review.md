# Crosstalk review trigger

Handle PR review round triggers as a peer.

Trigger:

```text
[crosstalk] review-round <NN> <agent> RUN_ID=<RUN_ID>
```

Read and follow:

```bash
cat /tmp/crosstalk/run-${RUN_ID}/rounds/r<NN>-<agent>.md
```

Do not answer the trigger directly. The round file contains the PR review material, transport instructions, response file path, and ping command.
