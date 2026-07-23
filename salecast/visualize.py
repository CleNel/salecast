import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

# Two of FEATURE_COLUMNS plotted directly, rather than a PCA projection -
# PCA components are unlabeled linear combinations of all 5 features, which
# reads as two meaningless axes to anyone looking at the chart. Discount
# depth and frequency are the two most intuitive of the five and carry most
# of the story on their own (see the same wording in api.py's
# CLUSTER_FEATURE_LABELS, kept consistent here).
X_FEATURE = "avg_discount_depth"
Y_FEATURE = "discount_frequency_per_year"
X_LABEL = "Average discount depth (%)"
Y_LABEL = "Discounts per year"


def plot_clusters(labeled: pd.DataFrame, output_path: str) -> None:
    """Scatter plot of X_FEATURE vs Y_FEATURE, colored by cluster_id."""
    fig, ax = plt.subplots(figsize=(8, 6))
    scatter = ax.scatter(
        labeled[X_FEATURE], labeled[Y_FEATURE], c=labeled["cluster_id"], cmap="tab10", s=12, alpha=0.8
    )
    ax.set_xlabel(X_LABEL)
    ax.set_ylabel(Y_LABEL)
    ax.set_title("Steam games clustered by discounting behavior")
    legend = ax.legend(*scatter.legend_elements(), title="Cluster")
    ax.add_artist(legend)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
