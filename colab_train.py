# ============================================================
# @caloriiibot — обучение модели распознавания еды (Food-101)
# Запускать в Google Colab: Runtime -> Change runtime type -> GPU (T4)
# Каждую ячейку отделяй по маркерам # %% [ячейка N]
# Результат: food_model.tflite + labels.txt (скачаются автоматически)
# ============================================================

# %% [ячейка 1] — зависимости (в Colab уже есть TF, ставим только tfds)
# !pip install -q tensorflow_datasets

# %% [ячейка 2] — загрузка Food-101 и подготовка
import tensorflow as tf
import tensorflow_datasets as tfds

IMG_SIZE = 224
BATCH = 64

(ds_train, ds_val), info = tfds.load(
    "food101",
    split=["train", "validation"],
    as_supervised=True,
    with_info=True,
)
NUM_CLASSES = info.features["label"].num_classes  # 101
class_names = info.features["label"].names

def prep(image, label):
    image = tf.image.resize(image, (IMG_SIZE, IMG_SIZE))
    image = tf.cast(image, tf.float32) / 255.0
    return image, label

AUTOTUNE = tf.data.AUTOTUNE
train = ds_train.map(prep, num_parallel_calls=AUTOTUNE).shuffle(2000).batch(BATCH).prefetch(AUTOTUNE)
val = ds_val.map(prep, num_parallel_calls=AUTOTUNE).batch(BATCH).prefetch(AUTOTUNE)

# %% [ячейка 3] — модель: MobileNetV2 + новая голова
base = tf.keras.applications.MobileNetV2(
    input_shape=(IMG_SIZE, IMG_SIZE, 3),
    include_top=False,
    weights="imagenet",
)
base.trainable = False  # сначала замораживаем backbone

model = tf.keras.Sequential([
    base,
    tf.keras.layers.GlobalAveragePooling2D(),
    tf.keras.layers.Dropout(0.2),
    tf.keras.layers.Dense(NUM_CLASSES, activation="softmax"),
])

model.compile(
    optimizer=tf.keras.optimizers.Adam(1e-3),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)

# %% [ячейка 4] — обучение: 3 эпохи голова + 2 эпохи fine-tune
model.fit(train, validation_data=val, epochs=3)

# размораживаем верхние слои backbone и дообучаем
base.trainable = True
for layer in base.layers[:-30]:
    layer.trainable = False

model.compile(
    optimizer=tf.keras.optimizers.Adam(1e-4),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)
model.fit(train, validation_data=val, epochs=2)

# %% [ячейка 5] — конвертация в TFLite + labels.txt
converter = tf.lite.TFLiteConverter.from_keras_model(model)
converter.optimizations = [tf.lite.Optimize.DEFAULT]  # квантизация -> ~9 МБ
tflite_model = converter.convert()

with open("food_model.tflite", "wb") as f:
    f.write(tflite_model)

with open("labels.txt", "w") as f:
    f.write("\n".join(class_names))

print("Готово:", len(class_names), "классов")

# %% [ячейка 6] — скачивание файлов
from google.colab import files
files.download("food_model.tflite")
files.download("labels.txt")
