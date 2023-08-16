<?php

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;
use App\Http\Controllers\PetsController;
use App\Http\Controllers\AuthController;

use App\Http\Controllers\LocationsController;



/*
|--------------------------------------------------------------------------
| API Routes
|--------------------------------------------------------------------------
|
| Here is where you can register API routes for your application. These
| routes are loaded by the RouteServiceProvider and all of them will
| be assigned to the "api" middleware group. Make something great!
|
*/


Route::middleware('auth:sanctum')->get('/user', function (Request $request) {
    return $request->user();
});


Route::middleware('auth:sanctum')->group(function () {
    Route::post('/logout', [AuthController::class, 'logout'])->name('user.logout');
    Route::resource('pets', "App\Http\Controllers\PetsController")->only(['index', 'show']);


});

//Move this to controller!!!
Route::get('images/{filename}', function ($filename)
{
    $path = 'storage/'. env('IMG_VIRTUAL_FILE_PATH') . $filename;

    if(!File::exists($path)) abort(404);

    $file = File::get($path);
    $type = File::mimeType($path);

    $response = Response::make($file, 200);
    $response->header("Content-Type", $type);

    return $response;
});

Route::get('pets/breeder/{id}', [PetsController::class, 'breeder'])->name('pets.breeder');

Route::post('/register', [AuthController::class, 'register'])->name('user.register');
Route::post('/login', [AuthController::class, 'login'])->name('user.login');
Route::get('/validatetoken', [AuthController::class, 'validatetoken'])->name('user.validatetoken');



Route::get('pets/imageUpload', [PetsController::class, 'uploadImage'])->name('pets.imageUpload');
Route::post('pets/delete', [PetsController::class, 'markDeleted'])->name('pets.delete');
Route::resource('pets', "App\Http\Controllers\PetsController")->only(['update', 'store']);
//Locations
Route::resource('locations', "App\Http\Controllers\LocationsController");
//Litters
Route::resource('litters', "App\Http\Controllers\LittersController");
Route::resource('breeds', "App\Http\Controllers\BreedsController");

