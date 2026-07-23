import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

# Two of FEATURE_COLUMNS plotted directly, rather than a PCA projection -
# PCA components are unlabeled linear combinations of all 5 features, which
# reads as two meaningless axes to anyone looking at the chart. Picked by
# checking which features actually separate the fitted clusters' means the
# most (discount_frequency_per_year barely differs by cluster - ~8.4/7.6/6.4
# - and made every group look like one overlapping blob; avg_discount_depth
# and time_to_first_discount_days differ by far more, e.g. one cluster
# averages ~75 days to its first discount vs ~1974 for another).
X_FEATURE = "avg_discount_depth"
Y_FEATURE = "time_to_first_discount_days"
X_LABEL = "Average discount depth (%)"
Y_LABEL = "Days to first discount"


def plot_clusters(labeled: pd.DataFrame, output_path: str) -> None:
    """Scatter plot of X_FEATURE vs Y_FEATURE, colored by cluster_id. Y uses
    a symlog scale since time_to_first_discount_days spans 0 to several
    thousand - a linear scale would squash most points into a thin band at
    the bottom under the few very-long-tail games."""
    fig, ax = plt.subplots(figsize=(8, 6))
    scatter = ax.scatter(
        labeled[X_FEATURE], labeled[Y_FEATURE], c=labeled["cluster_id"], cmap="tab10", s=12, alpha=0.8
    )
    ax.set_yscale("symlog", linthresh=30)
    ax.set_xlabel(X_LABEL)
    ax.set_ylabel(Y_LABEL)
    ax.set_title("Steam games clustered by discounting behavior")
    legend = ax.legend(*scatter.legend_elements(), title="Cluster")
    ax.add_artist(legend)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
