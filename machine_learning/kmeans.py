from sklearn.cluster import KMeans
import numpy as np
from sklearn import datasets
from pprint import pprint
import pandas as pd




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


iris = datasets.load_iris()
df = pd.DataFrame(iris.data, columns=FEATURES)
pprint(df.head(150))

def kmeans_example():
    # 150 rows x 4 features
    X = iris.data

    # the model. we have 3 clusters (because of 3 flower types)
    # the other params come from the example: https://scikit-learn.org/stable/modules/generated/sklearn.cluster.KMeans.html
    kmeans = KMeans(n_clusters=3, random_state=0, n_init="auto").fit(X)
    print(kmeans.labels_)

    # species can be guessed from the labels_:
    #     [150 rows x 4 columns]
    # [1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1
    #  1 1 1 1 1 1 1 1 1 1 1 1 1 2 0 2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
    #  0 0 0 2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 2 0 2 2 2 2 0 2 2 2 2
    #  2 2 0 0 2 2 2 2 0 2 0 2 0 2 2 0 0 2 2 2 2 2 0 2 2 2 2 0 2 2 2 0 2 2 2 0 2
    #  2 0]
    # these are the labels_; normally they start with 50x 0, then 50x1 then 50x2.
    # hence the clusters 1 and 0 are swtiched
    SPECIES = {1: "setosa", 0: "versicolor", 2: "virginica"}

    # loop: ask 4 metrics -> predict -> print species name
    while True:
        print("\nEnter 4 measurements in cm (or q to quit)")
        try:
            values = [ask_float(name) for name in FEATURES]
        except EOFError:
            break

        # [0] -> setosa, [1] -> versicolor, [2] -> virginica
        result = kmeans.predict(np.array([values]))
        label_idx = result[0]
        print(f"  predicted species: {SPECIES[label_idx]}  (class {label_idx}), {result=}")    


if __name__ == "__main__":
    kmeans_example()