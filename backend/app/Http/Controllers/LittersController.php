<?php

namespace App\Http\Controllers;

use App\Models\Litters;
use Illuminate\Http\Request;

class LittersController extends Controller
{

    public function index()
    {
        $litters = Litters::all();


        // Json Response
        return response()->json([
            'litters' => $litters
        ], 200);

    }

}
