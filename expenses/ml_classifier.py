"""
A real machine learning model (not an LLM API call) that predicts an
expense category from its title, using TF-IDF vectorization + a
Multinomial Naive Bayes classifier — both from scikit-learn.

The model trains fresh each time it's used, combining a small seed
dataset with the user's own expense history. This keeps things simple
(no model file to save/load) and means the model always reflects the
user's latest data.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

from .db import expenses_collection

# ---- Seed dataset: ensures the model works even for brand-new users ----
SEED_DATA = [
    # ---- Food ----
    ("Grocery shopping", "Food"),
    ("Lunch at restaurant", "Food"),
    ("Coffee", "Food"),
    ("Pizza order", "Food"),
    ("Dinner with friends", "Food"),
    ("Vegetables and fruits", "Food"),
    ("Snacks", "Food"),
    ("Breakfast at cafe", "Food"),
    ("Ice cream", "Food"),
    ("Milk and eggs", "Food"),
    ("Zomato order", "Food"),
    ("Swiggy delivery", "Food"),
    ("Street food", "Food"),
    ("Bakery items", "Food"),
    ("Chicken and meat", "Food"),
    ("Rice and dal", "Food"),
    ("Cold drink", "Food"),
    ("Tea and biscuits", "Food"),
    ("Burger King", "Food"),
    ("McDonald's meal", "Food"),
    ("Domino's pizza", "Food"),
    ("Fruits from market", "Food"),
    ("Bread and butter", "Food"),
    ("Juice bar", "Food"),
    ("Chocolate", "Food"),
    ("Cafe latte", "Food"),
    ("Restaurant bill", "Food"),
    ("Grocery store purchase", "Food"),
    ("Sweets for festival", "Food"),
    ("Canteen food", "Food"),

    # ---- Transport ----
    ("Uber ride", "Transport"),
    ("Bus ticket", "Transport"),
    ("Fuel for bike", "Transport"),
    ("Train ticket", "Transport"),
    ("Taxi fare", "Transport"),
    ("Parking fee", "Transport"),
    ("Ola cab", "Transport"),
    ("Petrol", "Transport"),
    ("Diesel refill", "Transport"),
    ("Auto rickshaw", "Transport"),
    ("Metro card recharge", "Transport"),
    ("Flight ticket", "Transport"),
    ("Car service", "Transport"),
    ("Bike repair", "Transport"),
    ("Toll tax", "Transport"),
    ("Rapido bike ride", "Transport"),
    ("Vehicle insurance", "Transport"),
    ("Cab to airport", "Transport"),
    ("Bus pass", "Transport"),
    ("Car wash", "Transport"),
    ("Rental car", "Transport"),
    ("Scooter fuel", "Transport"),
    ("Railway booking", "Transport"),
    ("Highway toll", "Transport"),

    # ---- Shopping ----
    ("New shoes", "Shopping"),
    ("Clothes shopping", "Shopping"),
    ("Amazon order", "Shopping"),
    ("Electronics purchase", "Shopping"),
    ("Gift for friend", "Shopping"),
    ("Book purchase", "Shopping"),
    ("Flipkart order", "Shopping"),
    ("New laptop", "Shopping"),
    ("Mobile phone", "Shopping"),
    ("Headphones", "Shopping"),
    ("Watch purchase", "Shopping"),
    ("Jeans and t-shirt", "Shopping"),
    ("Handbag", "Shopping"),
    ("Furniture purchase", "Shopping"),
    ("Home decor items", "Shopping"),
    ("Perfume", "Shopping"),
    ("Sunglasses", "Shopping"),
    ("Jewellery purchase", "Shopping"),
    ("Sports shoes", "Shopping"),
    ("Backpack", "Shopping"),
    ("Kitchen appliance", "Shopping"),
    ("Makeup products", "Shopping"),
    ("Toys for kids", "Shopping"),
    ("Online shopping", "Shopping"),

    # ---- Bills ----
    ("Electricity bill", "Bills"),
    ("Internet bill", "Bills"),
    ("Phone recharge", "Bills"),
    ("Rent payment", "Bills"),
    ("Water bill", "Bills"),
    ("Netflix subscription", "Bills"),
    ("Spotify subscription", "Bills"),
    ("Gas cylinder", "Bills"),
    ("Broadband bill", "Bills"),
    ("Mobile bill payment", "Bills"),
    ("DTH recharge", "Bills"),
    ("Maintenance charges", "Bills"),
    ("Amazon Prime subscription", "Bills"),
    ("Insurance premium", "Bills"),
    ("Loan EMI", "Bills"),
    ("Credit card bill", "Bills"),
    ("Cable TV bill", "Bills"),
    ("Society maintenance", "Bills"),
    ("YouTube Premium", "Bills"),
    ("Cloud storage subscription", "Bills"),
    ("House rent", "Bills"),
    ("Property tax", "Bills"),

    # ---- Other ----
    ("Movie tickets", "Other"),
    ("Gym membership", "Other"),
    ("Medicine", "Other"),
    ("Haircut", "Other"),
    ("Donation", "Other"),
    ("Doctor consultation", "Other"),
    ("Salon visit", "Other"),
    ("Concert tickets", "Other"),
    ("Books for study", "Other"),
    ("Stationery items", "Other"),
    ("Pet supplies", "Other"),
    ("Yoga class", "Other"),
    ("Birthday party expense", "Other"),
    ("Charity contribution", "Other"),
    ("Amusement park tickets", "Other"),
    ("Tuition fees", "Other"),
    ("Online course", "Other"),
    ("Medical checkup", "Other"),
    ("Spa treatment", "Other"),
    ("Photography service", "Other"),
    ("Repair service", "Other"),
    ("Printing and photocopy", "Other"),
    ("Wedding gift", "Other"),
    ("Miscellaneous expense", "Other"),
]

def _get_training_data(user_id):
    """Combines the seed dataset with this user's own past expenses."""
    titles = [row[0] for row in SEED_DATA]
    categories = [row[1] for row in SEED_DATA]

    user_expenses = expenses_collection.find({"user_id": user_id})
    for e in user_expenses:
        if e.get("title") and e.get("category"):
            titles.append(e["title"])
            categories.append(e["category"])

    return titles, categories


def predict_category(user_id, title):
    """
    Trains a fresh Naive Bayes model on this user's data (+ seed data),
    then predicts the category for the given title.
    Returns the predicted category string, or None if prediction fails.
    """
    if not title or not title.strip():
        return None

    titles, categories = _get_training_data(user_id)

    try:
        vectorizer = TfidfVectorizer()
        X = vectorizer.fit_transform(titles)

        model = MultinomialNB()
        model.fit(X, categories)

        title_vector = vectorizer.transform([title])
        prediction = model.predict(title_vector)

        return prediction[0]
    except Exception:
        return None


def evaluate_model_accuracy(user_id):
    """
    Splits the training data into train/test sets, trains on the
    train portion, and measures accuracy on the held-out test portion.
    This gives an honest estimate of how well the model generalizes,
    rather than just how well it memorized its own training data.
    """
    titles, categories = _get_training_data(user_id)

    if len(titles) < 10:
        return None  # not enough data for a meaningful train/test split

    try:
        X_train, X_test, y_train, y_test = train_test_split(
            titles, categories, test_size=0.25, random_state=42
        )

        vectorizer = TfidfVectorizer()
        X_train_vec = vectorizer.fit_transform(X_train)
        X_test_vec = vectorizer.transform(X_test)

        model = MultinomialNB()
        model.fit(X_train_vec, y_train)

        predictions = model.predict(X_test_vec)
        accuracy = accuracy_score(y_test, predictions)

        return round(accuracy * 100, 1)
    except Exception:
        return None