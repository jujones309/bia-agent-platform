import { KnowledgeBaseDetail } from "@/components/knowledge/KnowledgeBaseDetail";

/**
 * Shows a knowledge base with its documents.
 *
 * @param props.params - The route, with the base to open.
 * @returns The page.
 */
export default async function KnowledgeBasePage({ params }: { params: Promise<{ knowledgeBaseId: string }> }) {
  const { knowledgeBaseId } = await params;
  return <KnowledgeBaseDetail knowledgeBaseId={knowledgeBaseId} />;
}
