<?php

namespace App\Http\Controllers;

use App\Models\Breeds;
use Illuminate\Http\Request;

class BreedsController extends Controller
{
    public function index()
    {
        $breeds = Breeds::all();


        // Json Response
        return response()->json([
            'breeds' => $breeds
        ], 200);

    }
}
