"""
机器学习模型训练与验证
使用上午特征 + 日线特征预测次日涨跌
"""

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score, accuracy_score
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')


def load_and_prepare_data(csv_path: str) -> pd.DataFrame:
    """加载数据并进行基础预处理"""
    df = pd.read_csv(csv_path)

    # 移除无效行
    df = df.dropna(subset=['next_pct_chg'])

    return df


def get_feature_columns(df: pd.DataFrame, feature_set: str = "all") -> list:
    """
    获取特征列

    feature_set:
    - "basic": 仅基础日线特征
    - "morning": 仅上午特征
    - "all": 全部特征
    """
    # 基础日线特征
    basic_features = [
        'close', 'pct_chg', 'amplitude',
        'trend_short', 'trend_mid', 'ma_alignment', 'price_to_ma5',
        'rsi_6', 'kdj_k', 'kdj_d', 'kdj_j', 'price_pos_20',
        'volatility_5', 'volatility_20', 'volume_ratio',
        'up_days_5', 'up_days_10', 'consecutive_up', 'consecutive_down'
    ]

    # 上午特征（使用模拟的上午特征）
    morning_features = [
        col for col in df.columns
        if col.startswith('morning_') and col not in ['morning_n_bars', 'data_source']
    ]

    if feature_set == "basic":
        return [f for f in basic_features if f in df.columns]
    elif feature_set == "morning":
        return [f for f in morning_features if f in df.columns]
    else:
        all_features = basic_features + morning_features
        return [f for f in all_features if f in df.columns]


def train_and_evaluate(df: pd.DataFrame, feature_set: str = "all"):
    """训练并评估模型"""

    features = get_feature_columns(df, feature_set)

    if len(features) == 0:
        print(f"警告: 没有可用的{feature_set}特征")
        return None

    # 准备数据
    X = df[features].fillna(0)
    y = df['next_up']

    if len(X) < 50:
        print(f"样本数不足: {len(X)}")
        return None

    # 划分训练集和测试集
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y
    )

    # 标准化（仅对逻辑回归需要）
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    results = {}

    # 1. 随机森林
    rf = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
    rf.fit(X_train, y_train)
    rf_pred = rf.predict(X_test)
    rf_prob = rf.predict_proba(X_test)[:, 1]

    results['RandomForest'] = {
        'accuracy': accuracy_score(y_test, rf_pred),
        'auc': roc_auc_score(y_test, rf_prob),
        'model': rf,
        'feature_importance': dict(zip(features, rf.feature_importances_))
    }

    # 2. 梯度提升
    gb = GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42)
    gb.fit(X_train, y_train)
    gb_pred = gb.predict(X_test)
    gb_prob = gb.predict_proba(X_test)[:, 1]

    results['GradientBoosting'] = {
        'accuracy': accuracy_score(y_test, gb_pred),
        'auc': roc_auc_score(y_test, gb_prob),
        'model': gb,
        'feature_importance': dict(zip(features, gb.feature_importances_))
    }

    # 3. 逻辑回归
    lr = LogisticRegression(max_iter=1000, random_state=42)
    lr.fit(X_train_scaled, y_train)
    lr_pred = lr.predict(X_test_scaled)
    lr_prob = lr.predict_proba(X_test_scaled)[:, 1]

    results['LogisticRegression'] = {
        'accuracy': accuracy_score(y_test, lr_pred),
        'auc': roc_auc_score(y_test, lr_prob),
        'model': lr,
        'coef': dict(zip(features, lr.coef_[0]))
    }

    return results, X_test, y_test


def print_results(results: dict, feature_set: str):
    """打印评估结果"""

    print(f"\n{'='*80}")
    print(f"特征集: {feature_set}")
    print(f"{'='*80}")

    if results is None:
        print("无有效结果")
        return

    print(f"\n{'模型':<20} {'准确率':<12} {'AUC':<12}")
    print("-" * 50)

    for model_name, metrics in results.items():
        print(f"{model_name:<20} {metrics['accuracy']:.4f}      {metrics['auc']:.4f}")

    # 打印特征重要性（以随机森林为例）
    print(f"\n特征重要性 (RandomForest):")
    rf_importance = results['RandomForest']['feature_importance']
    sorted_importance = sorted(rf_importance.items(), key=lambda x: x[1], reverse=True)

    print(f"{'特征':<25} {'重要性':<12}")
    print("-" * 40)
    for feat, imp in sorted_importance[:10]:
        print(f"{feat:<25} {imp:.4f}")


def compare_feature_sets(df: pd.DataFrame):
    """比较不同特征集的效果"""

    print("="*80)
    print("特征集对比分析")
    print("="*80)

    feature_sets = ["basic", "morning", "all"]
    all_results = {}

    for fs in feature_sets:
        results, _, _ = train_and_evaluate(df, fs)
        all_results[fs] = results
        print_results(results, fs)

    # 对比总结
    print("\n" + "="*80)
    print("对比总结")
    print("="*80)

    print(f"\n{'特征集':<12} {'RandomForest AUC':<18} {'GradientBoosting AUC':<22} {'LogisticRegression AUC':<24}")
    print("-" * 80)

    for fs in feature_sets:
        if all_results[fs]:
            rf_auc = all_results[fs]['RandomForest']['auc']
            gb_auc = all_results[fs]['GradientBoosting']['auc']
            lr_auc = all_results[fs]['LogisticRegression']['auc']
            print(f"{fs:<12} {rf_auc:.4f}            {gb_auc:.4f}              {lr_auc:.4f}")

    # 找出最佳特征集
    best_fs = None
    best_auc = 0
    for fs in feature_sets:
        if all_results[fs]:
            auc = all_results[fs]['RandomForest']['auc']
            if auc > best_auc:
                best_auc = auc
                best_fs = fs

    print(f"\n最佳特征集: {best_fs} (AUC = {best_auc:.4f})")

    return all_results


def main():
    """主函数"""

    # 首先尝试加载已有的数据集
    data_path = Path(__file__).parent.parent / "output" / "training_dataset.csv"

    if not data_path.exists():
        print(f"数据文件不存在: {data_path}")
        print("请先运行 integrated_features.py 生成训练数据集")
        return

    print("加载训练数据...")
    df = load_and_prepare_data(str(data_path))
    print(f"样本数: {len(df)}")

    if len(df) < 100:
        print("样本数不足，无法进行有效训练")
        return

    # 对比不同特征集
    results = compare_feature_sets(df)

    print("\n" + "="*80)
    print("训练完成！")
    print("="*80)


if __name__ == "__main__":
    main()
