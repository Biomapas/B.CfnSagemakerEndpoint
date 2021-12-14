from typing import Iterable

from aws_cdk.aws_s3 import Bucket, EventType
from aws_cdk.aws_sagemaker import CfnEndpointConfigProps, CfnEndpointProps, CfnEndpoint, CfnEndpointConfig
from aws_cdk.core import Construct

from b_cfn_sagemaker_endpoint.bucket_event import BucketEvent
from b_cfn_sagemaker_endpoint.model_props import ModelProps
from b_cfn_sagemaker_endpoint.refresh.function import RefreshFunction


class SagemakerEndpoint(Construct):
    """
    SageMaker model inference endpoint.

    This resource enables deployed endpoint to be automatically updated when new model(-s) data is uploaded.
    It is designed to enable automatic update of SageMaker's models endpoint in the event of modifying the
    source model data. This is achieved by utilizing S3's' event notifications. On updating the target S3
    bucket objects, an event is emitted that is handled by a lambda function which updates the deployed
    SageMaker endpoint.

    :param scope: Construct scope.
    :param id: Scoped id of the resource.
    :param endpoint_props: Properties for defining a ``AWS::SageMaker::Endpoint``.
    :param endpoint_config_props: Properties for defining a ``AWS::SageMaker::EndpointConfig``.
    :param models_props: SageMaker models properties.
    :param models_bucket: Source S3 bucket for models data.
    :param bucket_events: Models data bucket events. By default, all ``models_bucket``
        objects events (``OBJECT_CREATED``) are handled.
    :param wait_time: Time to wait before endpoint is updated. It is useful to wait before
        handling s3 bucket events as there can be multiple other in-flight events coming.
        Default is 60 seconds.
    """

    def __init__(
            self,
            scope: Construct,
            id: str,
            endpoint_props: CfnEndpointProps,
            endpoint_config_props: CfnEndpointConfigProps,
            models_props: Iterable[ModelProps],
            models_bucket: Bucket,
            bucket_events: Iterable[BucketEvent] = None,
            wait_time: float = 60
    ):
        if endpoint_props.endpoint_config_name != endpoint_config_props.endpoint_config_name:
            raise ValueError(
                'Endpoint config name setting must be identical in the '
                '`endpoint_props` and the `endpoint_config_props` properties.'
            )

        if bucket_events is None:
            bucket_events = [
                BucketEvent(EventType.OBJECT_CREATED)
            ]

        super().__init__(scope, id)

        models = [props.bind(self) for props in models_props]
        endpoint_config_a = CfnEndpointConfig(
            scope=self,
            id=f'{id}AConfig',
            async_inference_config=endpoint_config_props.async_inference_config,
            data_capture_config=endpoint_config_props.data_capture_config,
            endpoint_config_name=f'{endpoint_config_props.endpoint_config_name}-a',
            kms_key_id=endpoint_config_props.kms_key_id,
            production_variants=endpoint_config_props.production_variants,
            tags=endpoint_config_props.tags,
        )
        endpoint_config_b = CfnEndpointConfig(
            scope=self,
            id=f'{id}BConfig',
            async_inference_config=endpoint_config_props.async_inference_config,
            data_capture_config=endpoint_config_props.data_capture_config,
            endpoint_config_name=f'{endpoint_config_props.endpoint_config_name}-b',
            kms_key_id=endpoint_config_props.kms_key_id,
            production_variants=endpoint_config_props.production_variants,
            tags=endpoint_config_props.tags,
        )
        endpoint_config_a.node.add_dependency(*models)
        endpoint_config_b.node.add_dependency(*models)

        self.__endpoint = CfnEndpoint(
            scope=self,
            id=id,
            deployment_config=endpoint_props.deployment_config,
            endpoint_config_name=endpoint_config_a.endpoint_config_name,
            endpoint_name=endpoint_props.endpoint_name,
            exclude_retained_variant_properties=endpoint_props.exclude_retained_variant_properties,
            retain_all_variant_properties=endpoint_props.retain_all_variant_properties,
            retain_deployment_config=endpoint_props.retain_deployment_config,
            tags=endpoint_props.tags,
        )
        self.__endpoint.node.add_dependency(endpoint_config_a, endpoint_config_b, *models)

        update_endpoint_function = RefreshFunction(
            scope=self,
            id=f'{id}RefreshFunction',
            endpoint=self.__endpoint,
            endpoint_config_a=endpoint_config_a,
            endpoint_config_b=endpoint_config_b,
            wait_time=wait_time
        )
        update_endpoint_function.node.add_dependency(self.__endpoint)
        for event in bucket_events:
            event.bind(models_bucket, update_endpoint_function)

    @property
    def endpoint_name(self) -> str:
        return self.__endpoint.endpoint_name

    @property
    def attr_endpoint_name(self) -> str:
        return self.__endpoint.attr_endpoint_name


__all__ = [
    'SagemakerEndpoint',
    'ModelProps',
    'BucketEvent'
]