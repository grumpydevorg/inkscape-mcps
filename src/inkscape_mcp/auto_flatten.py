"""Automatic parameter flattening for Pydantic models in FastMCP tools."""

import inspect
import json
import types
from functools import wraps
from typing import Union, get_args, get_origin

from pydantic import BaseModel, ValidationError
from pydantic_core._pydantic_core import PydanticUndefined


def flatten_pydantic_params(func):
    """Decorator that automatically flattens Pydantic model parameters."""

    # Get the original function signature
    sig = inspect.signature(func)

    # Track which parameters are Pydantic models and their field info
    pydantic_params = {}
    params_without_defaults = []
    params_with_defaults = []

    for param_name, param in sig.parameters.items():
        param_type = param.annotation

        # Check if this is a list of Pydantic models
        origin = get_origin(param_type)
        if origin is list:
            args = get_args(param_type)
            if (
                len(args) == 1
                and inspect.isclass(args[0])
                and issubclass(args[0], BaseModel)
            ):
                # Handle list[PydanticModel] - use JSON string parameter
                list_model_class = args[0]
                pydantic_params[param_name] = (
                    list_model_class,
                    True,
                )  # True indicates list

                # Create a single JSON string parameter for the list
                json_param = inspect.Parameter(
                    f"{param_name}_json",
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=str,
                    default=param.default
                    if param.default != inspect.Parameter.empty
                    else "[]",
                )

                if json_param.default == inspect.Parameter.empty:
                    params_without_defaults.append(json_param)
                else:
                    params_with_defaults.append(json_param)

        # Check if this is a Union type (like Export | None)
        elif get_origin(param_type) is Union or isinstance(param_type, types.UnionType):
            args = get_args(param_type)
            # Look for a Pydantic model in the union (ignoring None)
            pydantic_class = None
            for arg in args:
                if inspect.isclass(arg) and issubclass(arg, BaseModel):
                    pydantic_class = arg
                    break

            if pydantic_class is not None:
                # Handle Union with Pydantic model (like Export | None)
                pydantic_params[param_name] = (
                    pydantic_class,
                    False,
                    True,  # True indicates this is from a Union type
                )  # (class, is_list, is_union)

                # Add individual fields as parameters
                for field_name, field_info in pydantic_class.model_fields.items():
                    # Create parameter name by prefixing with original param name
                    new_param_name = f"{param_name}_{field_name}"

                    # Get the field type and default
                    field_type = field_info.annotation

                    # Handle Pydantic field defaults properly
                    if (
                        hasattr(field_info, "default")
                        and field_info.default is not ...
                        and field_info.default is not PydanticUndefined
                    ):
                        default_value = field_info.default
                    elif (
                        hasattr(field_info, "default_factory")
                        and field_info.default_factory is not None
                    ):
                        default_value = field_info.default_factory()
                    else:
                        # For optional Union types, make all fields optional
                        default_value = None

                    new_param = inspect.Parameter(
                        new_param_name,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=field_type,
                        default=default_value,
                    )

                    # For Union types, all fields get default None
                    # so they go to params_with_defaults
                    params_with_defaults.append(new_param)
            else:
                # Keep non-Pydantic Union parameters as-is
                if param.default == inspect.Parameter.empty:
                    params_without_defaults.append(param)
                else:
                    params_with_defaults.append(param)

        # Check if this is a simple Pydantic model
        elif inspect.isclass(param_type) and issubclass(param_type, BaseModel):
            # Handle simple Pydantic model (existing logic)
            pydantic_params[param_name] = (
                param_type,
                False,
                False,  # False indicates this is not from a Union type
            )  # (class, is_list, is_union)

            # Add individual fields as parameters
            for field_name, field_info in param_type.model_fields.items():
                # Create parameter name by prefixing with original param name
                new_param_name = f"{param_name}_{field_name}"

                # Get the field type and default
                field_type = field_info.annotation

                # Handle Pydantic field defaults properly
                if (
                    hasattr(field_info, "default")
                    and field_info.default is not ...
                    and field_info.default is not PydanticUndefined
                ):
                    default_value = field_info.default
                elif (
                    hasattr(field_info, "default_factory")
                    and field_info.default_factory is not None
                ):
                    default_value = field_info.default_factory()
                else:
                    default_value = inspect.Parameter.empty

                new_param = inspect.Parameter(
                    new_param_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=field_type,
                    default=default_value,
                )

                # Sort by whether they have defaults
                if default_value == inspect.Parameter.empty:
                    params_without_defaults.append(new_param)
                else:
                    params_with_defaults.append(new_param)

        else:
            # Keep non-Pydantic parameters as-is
            if param.default == inspect.Parameter.empty:
                params_without_defaults.append(param)
            else:
                params_with_defaults.append(param)

    # Combine parameters with required ones first
    new_params = params_without_defaults + params_with_defaults

    # Create new signature with flattened parameters
    new_sig = sig.replace(parameters=new_params)

    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Reconstruct Pydantic models from flattened parameters
        bound_args = new_sig.bind(*args, **kwargs)
        bound_args.apply_defaults()

        # Group parameters back into Pydantic models
        reconstructed_kwargs = {}
        remaining_kwargs = dict(bound_args.arguments)

        for original_param, model_info in pydantic_params.items():
            if isinstance(model_info, tuple):
                if len(model_info) >= 3:
                    model_class, is_list, is_union = model_info
                else:
                    # Handle old format for compatibility
                    model_class, is_list, is_union = model_info[0], model_info[1], False
            else:
                # Handle old format for compatibility
                model_class, is_list, is_union = model_info, False, False

            if is_list:
                # Handle list[PydanticModel] - parse from JSON
                json_param_name = f"{original_param}_json"
                if json_param_name in remaining_kwargs:
                    json_str = remaining_kwargs.pop(json_param_name)
                    try:
                        json_data = json.loads(json_str) if json_str else []
                        model_list = [model_class(**item) for item in json_data]
                        reconstructed_kwargs[original_param] = model_list
                    except (json.JSONDecodeError, TypeError):
                        # If JSON parsing fails, create empty list
                        reconstructed_kwargs[original_param] = []
                    except ValueError:
                        # Re-raise validation errors (like CSS selector validation)
                        raise
            else:
                # Handle single Pydantic model
                model_data = {}

                # Extract fields for this model
                for field_name in model_class.model_fields:
                    flattened_name = f"{original_param}_{field_name}"
                    if flattened_name in remaining_kwargs:
                        model_data[field_name] = remaining_kwargs.pop(flattened_name)

                # Create the Pydantic model instance
                if model_data:
                    # Only create model if we have actual data (not just None values)
                    non_none_data = {
                        k: v for k, v in model_data.items() if v is not None
                    }
                    if non_none_data:
                        try:
                            reconstructed_kwargs[original_param] = model_class(
                                **non_none_data
                            )
                        except ValidationError:
                            # If validation fails (e.g., missing required fields),
                            # leave as None for Union types
                            if is_union:
                                pass  # Leave as None
                            else:
                                raise  # Re-raise for non-Union types
                    # If only None values, leave the parameter as None

        # Add any remaining non-Pydantic parameters
        reconstructed_kwargs.update(remaining_kwargs)

        # Call the original function
        return await func(**reconstructed_kwargs)

    # Update the wrapper's signature for FastMCP introspection
    wrapper.__signature__ = new_sig
    wrapper.__annotations__ = {
        param.name: param.annotation
        for param in new_params
        if param.annotation != inspect.Parameter.empty
    }

    return wrapper
