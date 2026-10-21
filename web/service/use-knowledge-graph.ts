import { useMutation, useQueryClient } from '@tanstack/react-query'
import { consoleQuery } from './client'

export const useCreateKnowledgeGraph = () => {
  const queryClient = useQueryClient()

  return useMutation(consoleQuery.knowledgeGraphs.create.mutationOptions({
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: consoleQuery.knowledgeGraphs.list.key(),
      })
    },
  }))
}

export const useDeleteKnowledgeGraph = () => {
  const queryClient = useQueryClient()

  return useMutation(consoleQuery.knowledgeGraphs.delete.mutationOptions({
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: consoleQuery.knowledgeGraphs.list.key(),
      })
    },
  }))
}

export const useImportKnowledgeGraphTemplate = () => {
  const queryClient = useQueryClient()

  return useMutation(consoleQuery.knowledgeGraphs.importTemplate.mutationOptions({
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: consoleQuery.knowledgeGraphs.key(),
      })
    },
  }))
}
