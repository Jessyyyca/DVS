import matplotlib.pyplot as plt
from sklearn import datasets, svm
import pandas as pd
import mpl_toolkits.mplot3d  # noqa: F401
from pprint import pprint
import numpy as np

from sklearn.decomposition import PCA

iris = datasets.load_iris()
df = pd.DataFrame(iris.data, columns=["Sepal Length", "Sepal Width", "Petal Length", "Petal Width"])
pprint(df.head(150))

def plot_data_3d():
    """Plots a 3D Graph with Eigenvektoren of data"""
    fig = plt.figure(1, figsize=(8, 6))
    ax = fig.add_subplot(111, projection="3d", elev=-150, azim=110)



    X_reduced = PCA(n_components=3).fit_transform(iris.data)
    ax.scatter(
        X_reduced[:, 0],
        X_reduced[:, 1],
        X_reduced[:, 2],
        c=iris.target,
        s=40,
    )

    ax.set_title("First three PCA dimensions")
    ax.set_xlabel("1st Eigenvector")
    ax.xaxis.set_ticklabels([])
    ax.set_ylabel("2nd Eigenvector")
    ax.yaxis.set_ticklabels([])
    ax.set_zlabel("3rd Eigenvector")
    ax.zaxis.set_ticklabels([])

    plt.show()

# iris.target encodes the species as 0/1/2; map it back to a label
SPECIES = {0: "setosa", 1: "versicolor", 2: "virginica"}

# the four features the user has to type, in the order the dataset uses them
FEATURES = ("sepal length", "sepal width", "petal length", "petal width")


def ask_float(label: str) -> float:
    """Prompts until the user types a parseable float or q to quit"""
    while True:
        raw = input(f"{label} in cm: ")
        if raw.lower() == "q":
            raise SystemExit(0)
        try:
            return float(raw)
        except ValueError:
            print(f"  not a number, try again (e.g. 5.1)")


def svc_example():
    """
    Supervised learning example with iris dataset and SVC:
    Trains a model with a support vecor machine, to predict the flower class by its petal/sepal length/width
    """
    # x is 150 rows with 4 features each, y is the species class (0-2) for each row
    X = iris.data
    y = iris.target

    # poly with degree 13 means, that we build a function of degree 13 to
    # "draw the lines" between the dots. 13 is the amount my CPU can manage
    # in reasonable time
    clf = svm.SVC(kernel="poly", degree=13)
    clf.fit(X, y)

    # loop: ask 4 metrics -> predict -> print species name
    while True:
        print("\nEnter 4 measurements in cm (or q to quit)")
        try:
            values = [ask_float(name) for name in FEATURES]
        except EOFError:
            break

        # [0] -> setosa, [1] -> versicolor, [2] -> virginica
        label_idx = clf.predict(np.array([values]))[0]
        print(f"  predicted species: {SPECIES[label_idx]}  (class {label_idx})")    

if __name__ == "__main__":
    svc_example()

