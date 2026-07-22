import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from salecast.features import FEATURE_COLUMNS


def plot_clusters(labeled: pd.DataFrame, output_path: str) -> None:
    """Projects FEATURE_COLUMNS to 2D via PCA and saves a scatter plot
    colored by cluster_id."""
    X = StandardScaler().fit_transform(labeled[FEATURE_COLUMNS])
    coords = PCA(n_components=2, random_state=42).fit_transform(X)

    fig, ax = plt.subplots(figsize=(8, 6))
    scatter = ax.scatter(
        coords[:, 0], coords[:, 1], c=labeled["cluster_id"], cmap="tab10", s=12, alpha=0.8
    )
    ax.set_xlabel("PCA component 1")
    ax.set_ylabel("PCA component 2")
    ax.set_title("Steam games clustered by discounting behavior")
    legend = ax.legend(*scatter.legend_elements(), title="Cluster")
    ax.add_artist(legend)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
