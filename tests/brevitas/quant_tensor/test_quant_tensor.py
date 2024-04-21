# Copyright (C) 2024, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
from enum import Enum

import pytest
import torch

from brevitas.inject.enum import QuantType
from brevitas.nn import QuantIdentity
from brevitas.quant_tensor import QuantTensor


class Operator(Enum):
    ADD = 0
    SUBTRACT = 1
    DIVIDE = 2
    MULTIPLY = 3
    MATMUL = 4


def to_quant_tensor(input: torch.Tensor) -> QuantTensor:
    mod = QuantIdentity(bit_width=8, return_quant_tensor=True)
    return mod(input)


def to_quant_tensor_per_channel(input: torch.Tensor) -> QuantTensor:
    mod = QuantIdentity(
        bit_width=8,
        scaling_per_output_channel=True,
        per_channel_broadcastable_shape=(input.shape[0],) + (1,) * (input.ndim - 1),
        scaling_stats_permute_dims=tuple(range(input.ndim)),
        return_quant_tensor=True,
    )
    return mod(input)


def qdq(normal_tensor, quant_tensor):
    return (
        torch.round(normal_tensor / quant_tensor.scale + quant_tensor.zero_point) -
        quant_tensor.zero_point) * quant_tensor.scale


def test_quant_tensor_init():
    x = torch.randn(4, 4)
    quant_tensor = to_quant_tensor(x)
    normal_tensor = torch.Tensor(x)
    assert torch.allclose(qdq(normal_tensor, quant_tensor), quant_tensor, rtol=0.01)


@pytest.mark.parametrize(
    'op', [Operator.ADD, Operator.SUBTRACT, Operator.DIVIDE, Operator.MULTIPLY, Operator.MATMUL])
def test_quant_tensor_operators(op):
    # Avoid 0 values
    x = 1 + torch.rand(4, 4)

    a = torch.Tensor(x)
    b = torch.Tensor(x)

    qa = to_quant_tensor(a)
    qb = to_quant_tensor(b)

    # to factor in quantisation error
    e_a = a - qa
    e_b = b - qb

    if op == Operator.ADD:
        quant = qa + qb
        normal = (a - e_a) + (b - e_b)
    elif op == Operator.SUBTRACT:
        quant = qa - qb
        normal = (a - e_a) - (b - e_b)
    elif op == Operator.DIVIDE:
        quant = qa / qb
        normal = (a - e_a) / (b - e_b)
    elif op == Operator.MULTIPLY:
        quant = qa * qb
        normal = (a - e_a) * (b - e_b)
    elif op == Operator.MATMUL:
        # @ matmul operator not implemented for QuantTensor
        quant = torch.matmul(qa, qb)
        normal = (a - e_a) @ (b - e_b)
    else:
        # unrecognised operator
        assert False

    assert torch.allclose(normal, quant)


def test_quant_tensor_div_by_zero():
    a = to_quant_tensor(torch.ones(4, 4))
    b = to_quant_tensor(torch.zeros(4, 4))
    assert torch.isinf(a / b).all().item()


def test_quant_tensor_div_by_fraction():
    a = to_quant_tensor(torch.ones(4, 4))
    b = to_quant_tensor(torch.ones(4, 4) * 0.5)
    assert torch.allclose(a / b, torch.ones(4, 4) * 2, atol=0.1)


def test_quant_tensor_transpose():
    x = torch.ones(4, 4).tril()
    a = x.clone()
    a_transposed = a.transpose(0, 1)
    b = to_quant_tensor(x)
    b_transposed = b.transpose(0, 1)
    assert b_transposed.is_valid
    assert torch.allclose(a_transposed, b_transposed, atol=0.01)
    c = to_quant_tensor_per_channel(x)
    c_transposed = c.transpose(0, 1)
    assert c_transposed.is_valid
    assert torch.allclose(a_transposed, c_transposed, atol=0.01)


def test_quant_tensor_permute():
    x = torch.rand(4, 4, 4)
    a = x.clone()
    a_permuted = a.permute(1, 0, 2)
    b = to_quant_tensor(x)
    b_permuted = b.permute(1, 0, 2)
    assert b_permuted.is_valid
    assert torch.allclose(a_permuted, b_permuted, atol=0.01)
    c = to_quant_tensor_per_channel(x)
    c_permuted = c.permute(1, 0, 2)
    assert c_permuted.is_valid
    assert torch.allclose(a_permuted, c_permuted, atol=0.01)


def test_quant_tensor_squeeze():
    x = torch.rand(4, 1, 4, 1)
    a = x.clone()
    a_squeezed = a.squeeze()
    b = to_quant_tensor(x)
    b_squeezed = b.squeeze()
    assert b_squeezed.is_valid
    assert torch.allclose(a_squeezed, b_squeezed, atol=0.01)
    c = to_quant_tensor_per_channel(x)
    c_squeezed = c.squeeze()
    assert c_squeezed.is_valid
    assert torch.allclose(a_squeezed, c_squeezed, atol=0.01)


def test_quant_tensor_unsqueeze():
    x = torch.rand(4, 4)
    a = x.clone()
    a_unsqueezed = a.unsqueeze(1)
    b = to_quant_tensor(x)
    b_unsqueezed = b.unsqueeze(1)
    assert b_unsqueezed.is_valid
    assert torch.allclose(a_unsqueezed, b_unsqueezed, atol=0.01)
    c = to_quant_tensor_per_channel(x)
    c_unsqueezed = c.unsqueeze(1)
    assert c_unsqueezed.is_valid
    assert torch.allclose(a_unsqueezed, c_unsqueezed, atol=0.01)


# TODO: need to deal with quant metadata
def test_quant_tensor_view():
    x = torch.ones(4, 4)
    a = to_quant_tensor(x)
    b = torch.Tensor(x)

    assert torch.allclose(a.view(-1), b.view(-1), atol=0.01)
    assert torch.allclose(a.view(2, -1), b.view(2, -1), atol=0.01)
    assert torch.allclose(a.view(16, -1), b.view(16, -1), atol=0.01)
    assert torch.allclose(a.view(8, 2), b.view(8, 2), atol=0.01)
