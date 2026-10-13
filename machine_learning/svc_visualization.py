"""AI generated helpers to actually visualize our data"""

import matplotlib.pyplot as plt
from sklearn import datasets, svm
import pandas as pd
import mpl_toolkits.mplot3d  # noqa: F401
from pprint import pprint
import numpy as np

from sklearn.decomposition import PCA

iris = datasets.load_iris()

# iris.target encodes the species as 0/1/2; map it back to a label
SPECIES = {0: "setosa", 1: "versicolor", 2: "virginica"}

# the four features the user has to type, in the order the dataset uses them
FEATURES = ("sepal length", "sepal width", "petal length", "petal width")

def plot_svc_decision_boundary():
    """
    Plots the SVC's decision regions over a 2D slice of the iris feature space.

    Trains an SVC on petal length + petal width (the most separable pair)
    and shades every grid point by its predicted class, so each flower's dot
    sits in the region that the kernel assigned to it.
    """
    # petal length (col 2) + petal width (col 3) -> most separable pair
    X = iris.data[:, [2, 3]]
    y = iris.target

    clf = svm.SVC(kernel="poly", degree=14)
    clf.fit(X, y)

    # mesh a bit past min/max so the dots are not flush against the edge
    pad = 0.5
    x_min, x_max = X[:, 0].min() - pad, X[:, 0].max() + pad
    y_min, y_max = X[:, 1].min() - pad, X[:, 1].max() + pad
    xx, yy = np.meshgrid(
        np.linspace(x_min, x_max, 500),
        np.linspace(y_min, y_max, 500),
    )

    # predict every grid point -> one class index per pixel
    Z = clf.predict(np.c_[xx.ravel(), yy.ravel()]).reshape(xx.shape)

    fig, ax = plt.subplots(figsize=(8, 6))
    cmap = plt.cm.RdYlBu
    ax.contourf(xx, yy, Z, alpha=0.3, cmap=cmap)

    scatter = ax.scatter(
        X[:, 0],
        X[:, 1],
        c=y,
        s=40,
        edgecolors="k",
        cmap=cmap,
    )

    ax.set_xlabel("petal length (cm)")
    ax.set_ylabel("petal width (cm)")
    ax.set_title("SVC decision regions (RBF kernel)")
    ax.legend(
        scatter.legend_elements()[0],
        [SPECIES[i] for i in range(3)],
        title="species",
    )

    plt.show()


if __name__ == "__main__":
    plot_svc_decision_boundary()
    svc_example()

