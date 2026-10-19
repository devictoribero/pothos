# Answering review comments

A review comment is a claim about the code, not an order. Some are right, some are wrong, some are out of scope. Applying all of them is as bad as ignoring them.

## Gather

```bash
gh pr view <n> --json reviews,comments
gh api repos/{owner}/{repo}/pulls/<n>/comments --paginate
gh api graphql -f query='query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){reviewThreads(first:100){nodes{id isResolved comments(first:20){nodes{author{login __typename} body path line}}}}}}}' -F o=<owner> -F r=<repo> -F n=<n>
```

Work through unresolved threads, review bodies that list findings, and issue comments that ask for a change. Skip resolved threads and plain acknowledgements. A thread whose last comment is your own reply is waiting for its author: leave it.

## Decide, per comment

1. Read the code it points at, as it is now on the branch.
2. Check the claim against the code, the spec and the standards in the session context.
3. Decide: **apply** (the claim holds), **decline** (it does not, or it contradicts the spec or a standard) or **out of scope** (it holds but belongs to another ticket).

## Act

- Apply every accepted change in one commit, run `verify`, then push.
- Reply on each thread with what you did: the commit for an applied change, the reason for a decline, the follow-up for out of scope. Reply in the thread, not as a new comment:
  ```bash
  gh api graphql -f query='mutation($t:ID!,$b:String!){addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:$t,body:$b}){comment{id}}}' -F t=<thread id> -F b='<reply>'
  ```
- Resolve a thread only when its author is a bot (`__typename` is `Bot`) and the fix is pushed:
  ```bash
  gh api graphql -f query='mutation($t:ID!){resolveReviewThread(input:{threadId:$t}){thread{isResolved}}}' -F t=<thread id>
  ```
- A person's thread stays open for them to resolve. If a person asked for changes in a review, the gate keeps waiting until they approve or dismiss their review.

Report one line per comment: who, what they asked, and applied, declined (why) or out of scope.
