I've reviewed the `documents.ts` file, and you have good instincts—there are indeed several places where tenant isolation breaks down and could lead to a cross-tenant data leak.

Here are the main issues I spotted:
1. **`updateDocument`**: It updates documents strictly by `documentId` without checking the `session.tenantId`. This is a classic Insecure Direct Object Reference (IDOR) where a user could modify another tenant's document if they guess the ID.
2. **`exportWorkspace`**: The `tenantId` is being read directly from the client's request (`req.body.tenantId`) rather than the authenticated session. It's also vulnerable to SQL injection because it uses `$queryRawUnsafe` with string interpolation.
3. **`searchDocuments`**: The raw SQL query searches across the entire `documents` table without filtering for the session's `tenantId`.
4. **`adminListDocuments`**: The function only checks if the user is authenticated, but not if they are actually an admin, nor does it scope to a specific tenant.

I have created an **Implementation Plan** artifact outlining these issues and my proposed fixes. Please review the document—in particular, the **Open Questions** regarding how we should handle the `adminListDocuments` authorization and how we should pull the session data in `exportWorkspace`.

Let me know if the plan looks good or if you'd like to adjust any of the approaches!
{"answer":"I have reviewed `benchmarks/fixtures/documents.ts` and identified several cross-tenant data leaks and vulnerabilities. I've created an Implementation Plan artifact detailing the issues (IDOR in `updateDocument`, unverified client input and SQL injection in `exportWorkspace`, missing tenant scope in `searchDocuments`, and missing authorization in `adminListDocuments`) along with proposed fixes. Please review the plan in the artifacts panel and let me know if you approve or have any answers to the open questions!","toolAction":"Finishing task","toolSummary":"Finish the task"}