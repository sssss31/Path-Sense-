# Accessibility scoring

The score is a weighted 0–100 sum: road quality 25%, weather 20%, terrain 20%, historical risk 15%, current disruption 10%, vehicle suitability 10%. Weights live in application settings and can later move to an admin-managed database table.

Bands: 85–100 excellent, 70–84 good, 50–69 moderate, 30–49 high risk, 0–29 potentially inaccessible. The separate risk model produces transparent warnings; a future XGBoost model can implement the same interface.

