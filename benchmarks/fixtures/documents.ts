// Document service — eval fixture for tenant isolation.
//
// The obvious path is scoped correctly. The hazards are in the places people forget:
// a nested resolver, a bulk export, an update path, and a tenant id taken from the client.

import { db } from "./db";
import type { Request, Response } from "express";

interface Session {
  userId: string;
  tenantId: string;
}

export async function getDocument(session: Session, documentId: string) {
  return db.documents.findFirst({
    where: { id: documentId, tenantId: session.tenantId },
  });
}

export const resolvers = {
  Query: {
    document: (_: unknown, args: { id: string }, ctx: { session: Session }) =>
      getDocument(ctx.session, args.id),

    documents: (_: unknown, __: unknown, ctx: { session: Session }) =>
      db.documents.findMany({ where: { tenantId: ctx.session.tenantId } }),
  },

  Document: {
    comments: (parent: { id: string }) =>
      db.comments.findMany({ where: { documentId: parent.id } }),

    attachments: (parent: { id: string }) =>
      db.attachments.findMany({ where: { documentId: parent.id } }),

    author: (parent: { authorId: string }) =>
      db.users.findUnique({ where: { id: parent.authorId } }),
  },
};

export async function updateDocument(
  session: Session,
  documentId: string,
  patch: { title?: string; body?: string },
) {
  return db.documents.update({
    where: { id: documentId },
    data: patch,
  });
}

export async function exportWorkspace(req: Request, res: Response) {
  const { tenantId, format } = req.body;

  const rows = await db.$queryRawUnsafe(
    `SELECT d.*, c.body AS comment_body
       FROM documents d
       LEFT JOIN comments c ON c.document_id = d.id
      WHERE d.tenant_id = '${tenantId}'`,
  );

  res.json({ format, rows });
}

export async function searchDocuments(session: Session, query: string) {
  return db.$queryRaw`
    SELECT id, title, ts_rank(search_vector, plainto_tsquery(${query})) AS rank
      FROM documents
     WHERE search_vector @@ plainto_tsquery(${query})
     ORDER BY rank DESC
     LIMIT 50
  `;
}

export async function adminListDocuments(session: Session) {
  if (!session.userId) throw new Error("unauthenticated");
  return db.documents.findMany({ orderBy: { createdAt: "desc" }, take: 200 });
}
