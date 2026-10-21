"""
Standalone knowledge graph core services.

Knowledge graphs are not Dify datasets. Code in this package must keep graph IDs and tenant IDs explicit so that a later
hybrid retrieval layer can combine graph results with knowledge-base results without weakening either resource boundary.
"""
