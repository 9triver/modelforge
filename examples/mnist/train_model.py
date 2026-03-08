"""Train a simple CNN on MNIST digit recognition.

Pipeline inputs (from version artifact directories):
  datasets/MNIST/raw/              <- MNIST binary data (local)
  params/training_params.yaml      <- hyperparameters

Pipeline outputs:
  weights/mnist_cnn.pt             <- model weights (PyTorch state_dict)
  metrics.json                     <- evaluation metrics
"""

import json
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
from torchvision import datasets, transforms

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class SimpleCNN(nn.Module):
    """Small CNN for MNIST: 2 conv layers + 2 FC layers."""

    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2d(1, 16, 3, padding=1)
        self.conv2 = nn.Conv2d(16, 32, 3, padding=1)
        self.pool = nn.MaxPool2d(2, 2)
        self.fc1 = nn.Linear(32 * 7 * 7, 128)
        self.fc2 = nn.Linear(128, 10)

    def forward(self, x):
        x = self.pool(F.relu(self.conv1(x)))   # 28x28 -> 14x14
        x = self.pool(F.relu(self.conv2(x)))   # 14x14 -> 7x7
        x = x.view(x.size(0), -1)
        x = F.relu(self.fc1(x))
        x = self.fc2(x)
        return x


def train(
    data_dir="datasets",
    params_path="params/training_params.yaml",
    output_path="weights/mnist_cnn.pt",
):
    import yaml

    # -- 1. Load training params --
    params = {
        "epochs": 3,
        "batch_size": 64,
        "learning_rate": 0.001,
    }
    if Path(params_path).exists():
        with open(params_path) as f:
            cfg = yaml.safe_load(f)
        if cfg and "parameters" in cfg:
            params.update(cfg["parameters"])
        print("[训练配置] 从 " + params_path + " 加载参数")
    print("[训练配置] " + str(params))
    print("[训练配置] 设备: " + str(DEVICE))

    # -- 2. Load MNIST data --
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,)),
    ])

    Path(data_dir).mkdir(parents=True, exist_ok=True)
    train_dataset = datasets.MNIST(
        data_dir, train=True, download=False, transform=transform,
    )
    test_dataset = datasets.MNIST(
        data_dir, train=False, download=False, transform=transform,
    )

    train_loader = DataLoader(
        train_dataset, batch_size=params["batch_size"], shuffle=True,
    )
    test_loader = DataLoader(
        test_dataset, batch_size=1000, shuffle=False,
    )
    print("[数据准备] 训练集: " + str(len(train_dataset)) + " 张, "
          "测试集: " + str(len(test_dataset)) + " 张")

    # -- 3. Train --
    model = SimpleCNN().to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=params["learning_rate"])
    criterion = nn.CrossEntropyLoss()

    for epoch in range(params["epochs"]):
        model.train()
        running_loss = 0.0
        for batch_idx, (data, target) in enumerate(train_loader):
            data, target = data.to(DEVICE), target.to(DEVICE)
            optimizer.zero_grad()
            output = model(data)
            loss = criterion(output, target)
            loss.backward()
            optimizer.step()
            running_loss += loss.item()

        avg_loss = running_loss / len(train_loader)
        print("[训练] Epoch " + str(epoch + 1) + "/" + str(params["epochs"])
              + "  loss=" + "{:.4f}".format(avg_loss))

    # -- 4. Evaluate --
    model.eval()
    correct = 0
    total = 0
    per_class_correct = [0] * 10
    per_class_total = [0] * 10

    with torch.no_grad():
        for data, target in test_loader:
            data, target = data.to(DEVICE), target.to(DEVICE)
            output = model(data)
            _, predicted = torch.max(output, 1)
            total += target.size(0)
            correct += (predicted == target).sum().item()
            for i in range(target.size(0)):
                label = target[i].item()
                per_class_total[label] += 1
                if predicted[i].item() == label:
                    per_class_correct[label] += 1

    accuracy = correct / total
    per_class_acc = {}
    for digit in range(10):
        if per_class_total[digit] > 0:
            per_class_acc[str(digit)] = round(
                per_class_correct[digit] / per_class_total[digit], 4,
            )

    metrics = {
        "accuracy": round(accuracy, 4),
        "test_samples": total,
        "train_samples": len(train_dataset),
        "per_class_accuracy": per_class_acc,
    }
    print("[模型产出] accuracy=" + "{:.4f}".format(accuracy)
          + " (" + str(correct) + "/" + str(total) + ")")

    # -- 5. Save model --
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    # Save as TorchScript for portable deployment (no class definition needed)
    model.cpu()
    scripted = torch.jit.script(model)
    scripted.save(output_path)
    print("[模型产出] 权重已保存 (TorchScript): " + output_path)

    with open("metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    return metrics


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Train MNIST CNN")
    p.add_argument("--data-dir", default="datasets")
    p.add_argument("--params", default="params/training_params.yaml")
    p.add_argument("--output", default="weights/mnist_cnn.pt")
    args = p.parse_args()
    train(args.data_dir, args.params, args.output)
