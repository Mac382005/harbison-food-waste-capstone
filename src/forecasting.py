from __future__ import annotations

import pandas as pd


def forecast(df, food, meal, area):
    sub = df[(df.food_item == food) & (df.meal == meal) & (df.waste_type == "Production Waste")].copy()
    if area != "All":
        sub = sub[sub.service_area == area]
    sub = sub.sort_values("service_date")
    if sub.empty:
        return {"n":0,"avg":None,"rec":None,"baseline_mae":None,"model_mae":None,"message":"No production-waste history for this selection."}

    sub["usable"] = pd.to_numeric(sub.prepared_kg, errors="coerce") - pd.to_numeric(sub.waste_kg, errors="coerce")
    sub = sub.dropna(subset=["usable"])
    n = len(sub)
    if n < 3:
        return {"n":n,"avg":None,"rec":None,"baseline_mae":None,"model_mae":None,"message":"Insufficient history. Continue collecting data."}

    recent = sub.tail(min(8,n))
    avg = float(recent.usable.mean())
    rec = avg * 1.06

    baseline_mae = None
    if n >= 5:
        vals = sub.usable.tolist()
        actual, preds = [], []
        for i in range(3, len(vals)):
            hist = vals[max(0,i-4):i]
            preds.append(sum(hist)/len(hist))
            actual.append(vals[i])
        if actual:
            baseline_mae = sum(abs(a-p) for a,p in zip(actual,preds))/len(actual)

    model_mae = None
    if n >= 30:
        try:
            from sklearn.ensemble import RandomForestRegressor
            from sklearn.metrics import mean_absolute_error
            from sklearn.model_selection import train_test_split
            work = sub.copy()
            work["dow"] = work.service_date.dt.dayofweek
            work["week"] = work.service_date.dt.isocalendar().week.astype(int)
            work["resident_count"] = pd.to_numeric(work.resident_count, errors="coerce").fillna(
                pd.to_numeric(work.resident_count, errors="coerce").median()
            )
            X = work[["dow","week","resident_count"]].fillna(0)
            y = work.usable
            Xtr,Xte,ytr,yte = train_test_split(X,y,test_size=.25,random_state=42)
            model = RandomForestRegressor(n_estimators=120,random_state=42,min_samples_leaf=2)
            model.fit(Xtr,ytr)
            model_mae = float(mean_absolute_error(yte,model.predict(Xte)))
        except Exception:
            pass

    return {
        "n":n,"avg":avg,"rec":rec,"baseline_mae":baseline_mae,"model_mae":model_mae,
        "message":"Recommendation = recent usable requirement average + 6% buffer. Decision support only."
    }
