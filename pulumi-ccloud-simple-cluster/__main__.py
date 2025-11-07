'''A Python Pulumi program'''

import json
import pulumi
import pulumi_confluentcloud as confluentcloud

config = pulumi.Config()
confluentcloud_provider = config.require('confluentcloud_provider')
confluentcloud_region = config.require('confluentcloud_region')
confluentcloud_environment_name = config.require('confluentcloud_environment_name')
confluentcloud_service_account_name = config.require('confluentcloud_service_account_name')
confluentcloud_cluster_name = config.require('confluentcloud_cluster_name')
confluentcloud_cluster_type = config.require('confluentcloud_cluster_type')
confluentcloud_test_topic = config.require('confluentcloud_test_topic')

stack = pulumi.get_stack()

# use the next line if the environment does not exist yet
# env = confluentcloud.Environment(confluentcloud_environment_name, display_name=confluentcloud_environment_name)
# use the next line instead if the environment already exists and shall be imported
env = confluentcloud.get_environment(display_name=confluentcloud_environment_name)
if confluentcloud_cluster_type.upper() == "BASIC":
    cluster_type_arg={
            'basic': {}
        }
elif confluentcloud_cluster_type.upper() == "STANDARD":
    cluster_type_arg={
            'standard': {}
        }
elif confluentcloud_cluster_type.upper() == "ENTERPRISE":
    cluster_type_arg={
            'enterprise': {}
        }
elif confluentcloud_cluster_type.upper() == "DEDICATED":
    cluster_type_arg={
            'dedicated': {
                'cku': 1
            }
        }
elif confluentcloud_cluster_type.upper() == "FREIGHT":
    cluster_type_arg={
            'freights': [{}]
        }

basic = confluentcloud.KafkaCluster(confluentcloud_cluster_name,
    display_name=confluentcloud_cluster_name,
    availability='SINGLE_ZONE',
    cloud=confluentcloud_provider,
    region=confluentcloud_region,
    environment={
        'id': env.id,
    },
    **cluster_type_arg
)

basic_cluster_admin_sa = confluentcloud.ServiceAccount(confluentcloud_service_account_name, 
                                                       description='Test, Delete if required', 
                                                       display_name=confluentcloud_service_account_name)

basic_cluster_admin_api_key = confluentcloud.ApiKey(f'{confluentcloud_service_account_name}_cluster_api_key',
                                                    managed_resource={
                                                        'api_version': basic.api_version,
                                                        'id': basic.id,
                                                        'kind': basic.kind,
                                                        'environment': {
                                                            'id': env.id
                                                        }
                                                    },
                                                    owner={
                                                        'api_version': basic_cluster_admin_sa.api_version,
                                                        'kind': basic_cluster_admin_sa.kind,
                                                        'id': basic_cluster_admin_sa.id
                                                    }
                                                    )
# Note the use of the "apply" method with a lambda when using the service account ID.
# This is required as that ID is actually and output of a create/update of some infrastructure elements and only known after that operation.
# Actually, it is implemented as a future. "apply" will be called only after the CRUD operation has completed, thus delaying the creation of the whole Role binding.
# This wouldn't be possible if just using the ID as a string object.
basic_cluster_admin_rbac = confluentcloud.RoleBinding(f'{confluentcloud_service_account_name}_cluster_role_binding_cluster_admin',
                                                    #principal='User:'+basic_cluster_admin_sa.id,
                                                    principal=basic_cluster_admin_sa.id.apply(lambda the_id: f'User:{the_id}'),
                                                    role_name='CloudClusterAdmin',
                                                    crn_pattern=basic.rbac_crn
)

topic = confluentcloud.KafkaTopic(confluentcloud_test_topic, 
                                    topic_name = confluentcloud_test_topic, 
                                    rest_endpoint = basic.rest_endpoint,
                                    
                                    kafka_cluster={
                                        'id': basic.id
                                    },
                                    credentials={
                                        'key': basic_cluster_admin_api_key.id,
                                        'secret': basic_cluster_admin_api_key.secret
                                    },
                                    opts=pulumi.ResourceOptions(depends_on=basic_cluster_admin_rbac)
                                    )

schema_registry = confluentcloud.get_schema_registry_cluster(environment={
        'id': env.id,
    })

schema_registry_resource_owner_api_key = confluentcloud.ApiKey(f'{confluentcloud_service_account_name}_schema_registry_resource_owner_api_key',
                                                    managed_resource={
                                                        'api_version': schema_registry.api_version,
                                                        'id': schema_registry.id,
                                                        'kind': schema_registry.kind,
                                                        'environment': {
                                                            'id': env.id
                                                        }
                                                    },
                                                    owner={
                                                        'api_version': basic_cluster_admin_sa.api_version,
                                                        'kind': basic_cluster_admin_sa.kind,
                                                        'id': basic_cluster_admin_sa.id
                                                    }
                                                    )

schema_registry_role_binding_admin = confluentcloud.RoleBinding(f'{confluentcloud_cluster_name}_schema_registry_admin_rb',
                                                    principal=basic_cluster_admin_sa.id.apply(lambda the_id: f'User:{the_id}'),
                                                    role_name='ResourceOwner',
                                                    #crn_pattern=schema_registry.resource_name.apply(lambda the_crn: f'{the_crn}/subject={confluentcloud_test_topic}-*')
                                                    crn_pattern=f'{schema_registry.resource_name}/subject={confluentcloud_test_topic}-*'
                                                    )

schema_data = {
    'type': 'record',
    'name': 'io.confluent.pulumi.schema.example.record',
    'doc': 'This is an example schema',
    'fields': [
        {
            'name':'name',
            'type':'string'
        }
    ]
}
# schema_data = {
#     'type': 'record',
#     'name': 'io.confluent.pulumi.schema.example.record',
#     'doc': 'This is an example schema',
#     'fields': [
#         {
#             'name':'name',
#             'type':'string'
#         },
#         {
#             'name':'value',
#             'type':'double',
#             'default':0.0
#         }
#     ]
# }

# When using recreate_on_update=False, you can just comment the first "schema_data" definition and uncomment the second before runing Pulumi again
# A new version of the schema will be created in Schema Registry, the original version (actually all older versions) become orphaned in SR.
# When running "pulumi destroy", these older versions are not deleted and remain in SR.

schema = confluentcloud.Schema(f'{confluentcloud_test_topic}-value',
    subject_name=f'{confluentcloud_test_topic}-value',
    format='AVRO',
    schema=json.dumps(schema_data),
    hard_delete=True,
    recreate_on_update=False, # Use this if Pulumi should not track all versions of a schema
    # recreate_on_update=True, # Use this instead, if Pulumi should track and manage all versions of a schema
    rest_endpoint=schema_registry.rest_endpoint,
    schema_registry_cluster={
        'id': schema_registry.id,
    },
    credentials={
        'key': schema_registry_resource_owner_api_key.id,
        'secret': schema_registry_resource_owner_api_key.secret
    },
    opts=pulumi.ResourceOptions(depends_on=schema_registry_role_binding_admin)
    )

# Alternatively, you can manage each schema version in Pulumi explicitly. 
# Just set "recreate_on_update=True" above and uncomment the lines below.
# A new version of the same contract (with the same subject) will be created, but Pulumi will keep track of all versions configured in this config
# This means, Pulumi will also do the house keeping, i.e. deleting all schemas when deleting the whole stack.

# schema_data_v2 = {
#     'type': 'record',
#     'name': 'io.confluent.pulumi.schema.example.record',
#     'doc': 'This is an example schema',
#     'fields': [
#         {
#             'name':'name',
#             'type':'string'
#         },
#         {
#             'name':'value',
#             'type':'double',
#             'default':0.0
#         }
#     ]
# }

# # A newer version of the schema. Note that the previous schema version has been added to the "depends_on" list.
# # This guarantees a clean order when creating the schemas in one run. Just make sure to remove the "schema" object from the list if you have deleted it from Pulumi for testing
# schema_v2 = confluentcloud.Schema(f'{confluentcloud_test_topic}-value-v2',
#     subject_name=f'{confluentcloud_test_topic}-value',
#     format='AVRO',
#     schema=json.dumps(schema_data_v2),
#     hard_delete=True,
#     recreate_on_update=True,
#     rest_endpoint=schema_registry.rest_endpoint,
#     schema_registry_cluster={
#         'id': schema_registry.id,
#     },
#     credentials={
#         'key': schema_registry_resource_owner_api_key.id,
#         'secret': schema_registry_resource_owner_api_key.secret
#     },
#     opts=pulumi.ResourceOptions(depends_on=[schema_registry_role_binding_admin, schema]) # Use this line as long as you stil have the "schema" object defined above
#     #opts=pulumi.ResourceOptions(depends_on=[schema_registry_role_binding_admin]) # If you have remove/commented the "schema" object, use this dependency relation, instead
#     )
