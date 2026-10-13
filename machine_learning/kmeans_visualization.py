"""
AI-generated helper for visualization

Visualize KMeans clusters on the iris dataset.

Fits KMeans with k=3 on all four iris features and saves a PNG that
shows the data points colored by cluster assignment, the cluster
centroids, and (for reference) the true species side by side.
"""
import numpy as np
import matplotlib.pyplot as plt
from sklearn import datasets
from sklearn.cluster import KMeans

# iris.target encodes the species as 0/1/2; map it back to a label
SPECIES = {0: "setosa", 1: "versicolor", 2: "virginica"}
FEATURES = ("sepal length", "sepal width", "petal length", "petal width")

# petal length vs. petal width gives the cleanest visual separation
# between the three iris species
X_IDX = FEATURES.index("petal length")
Y_IDX = FEATURES.index("petal width")

OUT_PATH = "kmeans_clusters.png"
K = 3


def fit_kmeans(X: np.ndarray) -> KMeans:
    return KMeans(n_clusters=K, random_state=0, n_init="auto").fit(X)


def plot_panel(ax, X, colors, title: str, centers=None) -> None:
    ax.scatter(
        X[:, X_IDX],
        X[:, Y_IDX],
        c=colors,
        cmap="viridis",
        s=35,
        edgecolor="k",
        linewidth=0.3,
    )
    if centers is not None:
        ax.scatter(
            centers[:, X_IDX],
            centers[:, Y_IDX],
            c="red",
            marker="X",
            s=220,
            edgecolor="black",
            linewidth=1.5,
            label="centroid",
        )
        ax.legend(loc="upper left")
    ax.set_xlabel(f"{FEATURES[X_IDX]} (cm)")
    ax.set_ylabel(f"{FEATURES[Y_IDX]} (cm)")
    ax.set_title(title)


def main(out_path: str = OUT_PATH) -> None:
    iris = datasets.load_iris()
    X = iris.data

    kmeans = fit_kmeans(X)
    labels = kmeans.labels_

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # left: points colored by the kmeans cluster they were assigned to,
    # centroids overlaid as red X markers
    plot_panel(
        axes[0],
        X,
        labels,
        f"KMeans clusters (k={K})",
        centers=kmeans.cluster_centers_,
    )

    # right: same points colored by their true species, so the eye can
    # see how well the clusters line up with the ground truth
    plot_panel(axes[1], X, iris.target, "True species")

    fig.suptitle("Iris dataset: KMeans vs. ground truth")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    print(f"saved {out_path}")


if __name__ == "__main__":
    main()
