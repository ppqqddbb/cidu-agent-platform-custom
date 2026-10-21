import KnowledgeGraphDetail from '@/app/components/knowledge-graphs/detail'

type KnowledgeGraphDetailPageProps = {
  params: Promise<{
    graphId: string
  }>
}

const KnowledgeGraphDetailPage = async ({ params }: KnowledgeGraphDetailPageProps) => {
  const { graphId } = await params
  return <KnowledgeGraphDetail graphId={graphId} />
}

export default KnowledgeGraphDetailPage
