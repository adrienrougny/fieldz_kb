import fieldz_kb.neo4j.core


class Adapter(object):
    def __init__(self, obj):
        self.obj = obj

    def get_nodes_and_relationships(self):
        nodes, to_connect = fieldz_kb.neo4j.core.make_nodes_from_object(self.obj)
        biocypher_nodes = []
        biocypher_relationships = []
        for node in nodes:
            id_ = node.id_
            label = node.__label__
            properties = node.__properties__
            properties = {
                key: value
                for key, value in node.__properties__.items()
                if value is not None
            }
            biocypher_node = (
                id_,
                label,
                properties,
            )
            biocypher_nodes.append(biocypher_node)
        for relationship in to_connect:
            source_node = relationship[0]
            source_node_id = source_node.id_
            target_node_id = relationship[2].id_
            attr_name = relationship[1]
            label = getattr(type(source_node), attr_name).definition["relation_type"]
            properties = relationship[3]
            properties = {
                key: value
                for key, value in node.__properties__.items()
                if value is not None
            }
            biocypher_relationship = (source_node_id, target_node_id, label, properties)
            biocypher_relationships.append(biocypher_relationship)
        return biocypher_nodes, biocypher_relationships
